"""Phase 2 cross-table join — the deterministic *enrich* prepare stage.

Attaches a column from a related table onto a base relation's rows by following the
schema's foreign-key graph, so downstream (Phase-1 filter, aggregation, Step 1/2/3)
sees it as an ordinary extra attribute — nothing else changes (see join/PLAN.md).

FK graph edges:
  forward  child.fk_cols -> parent.pk_cols   (child holds an FK; always 1:1, no multiply)
  reverse  parent.pk_cols -> child.fk_cols   (step into a child/bridge). A reverse hop
           MULTIPLIES only when the child's PK has columns beyond the FK
           (encompasses PK [country,continent] > FK [country]); a reverse hop into a
           child whose PK == FK is 1:1 and does not multiply (economy PK [country]).

Standard library only, no gold knowledge (schema + rows only, so the blind/gold
separation invariant is preserved).

Join spec (carried with filters/aggregate)::

    { "table": "country_population",
      "joins": [ { "bring": "encompasses.continent", "as": "continent", "policy": "first" } ] }

`bring` = "<table>.<column>"; the engine finds the shortest FK path. `policy` is `first`
(default; keep one match, cardinality preserved) or `explode` (one row per match; only
matters on a multiplying hop). An empty/absent `joins` list is the identity.

Run offline::

    python schemavislm/join/join_tables.py --schema schema.json --data data.json \
        --spec join_spec.json --out rows.json
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from typing import Any


def _norm(s: Any) -> str:
    return s.lower() if isinstance(s, str) else s


def _get(row: dict, col: str):
    if col in row:
        return row[col]
    cn = _norm(col)
    for k, v in row.items():
        if _norm(k) == cn:
            return v
    return None


def _tables(schema):
    return schema.get("tables", {}) if isinstance(schema, dict) else {}


def _find_table(schema, name):
    for tname, tdef in _tables(schema).items():
        if _norm(tname) == _norm(name):
            return tname, tdef
    return None, None


def fk_graph(schema):
    """table name -> list of hops {to, on:[(from_col,to_col)], reverse, multiplies}."""
    graph: dict[str, list] = {}
    for cname, cdef in _tables(schema).items():
        cpk = [_norm(c) for c in cdef.get("primary_key", [])]
        for fk in cdef.get("foreign_keys", []):
            ref = fk.get("references_table")
            _, rdef = _find_table(schema, ref)
            if rdef is None:
                continue
            fkcols = fk.get("columns", [])
            refpk = rdef.get("primary_key", [])
            if len(fkcols) != len(refpk):
                # can only join on a matching-arity FK -> PK correspondence
                continue
            # forward: child -> parent (1:1)
            graph.setdefault(cname, []).append({
                "to": ref, "on": list(zip(fkcols, refpk)),
                "reverse": False, "multiplies": False,
            })
            # reverse: parent -> child; multiplies iff child PK has cols beyond the FK
            multiplies = set(_norm(c) for c in fkcols) != set(cpk)
            graph.setdefault(ref, []).append({
                "to": cname, "on": list(zip(refpk, fkcols)),
                "reverse": True, "multiplies": multiplies,
            })
    return graph


def find_paths(schema, base_table, target_table):
    """Shortest FK path(s) base -> target. Each element is a list of hops with a `frm`
    field added. Returns [] if unreachable."""
    graph = fk_graph(schema)
    base, _ = _find_table(schema, base_table)
    target, _ = _find_table(schema, target_table)
    if base is None or target is None:
        return []
    q = deque([(base, [])])
    seen = {base}
    found = []
    found_len = None
    while q:
        node, path = q.popleft()
        if found_len is not None and len(path) > found_len:
            break
        if node == target and path:
            found.append(path)
            found_len = len(path)
            continue
        for hop in graph.get(node, []):
            if hop["to"] not in seen or hop["to"] == target:
                if hop["to"] not in seen:
                    seen.add(hop["to"])
                q.append((hop["to"], path + [dict(hop, frm=node)]))
    return found


def reachable_columns(schema, base_table, max_hops=2):
    """Every foreign column offerable for a base table (bounded hop count), each with
    its path and whether attaching it can multiply rows."""
    base, _ = _find_table(schema, base_table)
    if base is None:
        return []
    graph = fk_graph(schema)
    # BFS recording the shortest path to each table
    best: dict[str, list] = {}
    q = deque([(base, [])])
    seen = {base}
    while q:
        node, path = q.popleft()
        if len(path) >= max_hops:
            continue
        for hop in graph.get(node, []):
            nxt = hop["to"]
            npath = path + [dict(hop, frm=node)]
            if nxt not in seen:
                seen.add(nxt)
                best[nxt] = npath
                q.append((nxt, npath))
    out = []
    for tname, path in best.items():
        _, tdef = _find_table(schema, tname)
        if tdef is None:
            continue
        multiplies = any(h["multiplies"] for h in path)
        join_cols = {_norm(tc) for h in path for (_, tc) in h["on"]}
        for c in tdef.get("columns", []):
            cn = c.get("name")
            if _norm(cn) in join_cols:
                continue  # the join key itself is not an interesting attribute
            out.append({"table": tname, "column": cn, "path": path, "multiplies": multiplies})
    return out


def _index(rows, to_cols):
    idx: dict[tuple, list] = {}
    for r in rows or []:
        if isinstance(r, dict):
            key = tuple(_get(r, tc) for tc in to_cols)
            idx.setdefault(key, []).append(r)
    return idx


def _resolve(schema, base_table, join):
    """Return (path, target_table, bring_col) for a join spec."""
    if isinstance(join.get("path"), list) and join.get("column"):
        path = join["path"]
        target = path[-1]["to"] if path else base_table
        return path, target, join["column"]
    bring = join.get("bring") or ""
    if "." not in bring:
        return None, None, None
    target, col = bring.split(".", 1)
    paths = find_paths(schema, base_table, target)
    return (paths[0] if paths else None), target, col


def enrich(schema, tables_data, base_table, base_rows, joins):
    """Attach each join's column to the base rows via its FK path.

    `first` keeps one deterministic match per row (cardinality preserved); `explode`
    emits one row per match on a multiplying hop. A path of only forward / 1:1-reverse
    hops never multiplies. Left-join semantics: an unmatched row keeps a None value.
    Never mutates input rows.
    """
    rows = [dict(r) for r in (base_rows or []) if isinstance(r, dict)]
    existing = set()
    for r in rows[:1]:
        existing = {_norm(k) for k in r.keys()}
    for join in joins or []:
        path, target, bring_col = _resolve(schema, base_table, join)
        if not path or not bring_col:
            continue
        as_col = join.get("as") or bring_col
        if _norm(as_col) in existing:
            as_col = str(target) + "__" + str(bring_col)
        policy = (join.get("policy") or "first").lower()
        indexes = [_index(tables_data.get(hop["to"], []), [tc for (_, tc) in hop["on"]]) for hop in path]

        new_rows = []
        for r in rows:
            frontiers = [r]  # rows in the previous hop's table space; start = base row
            for hop, idx in zip(path, indexes):
                nxt = []
                for fr in frontiers:
                    key = tuple(_get(fr, fc) for (fc, _) in hop["on"])
                    matches = idx.get(key, [])
                    if not matches:
                        continue
                    if hop["multiplies"] and policy == "explode":
                        nxt.extend(matches)
                    else:
                        nxt.append(min(matches, key=lambda m: json.dumps(
                            {k: str(v) for k, v in sorted(m.items())}, sort_keys=True)))
                frontiers = nxt
            if not frontiers:
                nr = dict(r); nr[as_col] = None; new_rows.append(nr)
            else:
                for fr in frontiers:
                    nr = dict(r); nr[as_col] = _get(fr, bring_col); new_rows.append(nr)
        rows = new_rows
        existing.add(_norm(as_col))
    return rows


def _rows_for_table(data, table):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("tables"), dict):
            for k, rows in data["tables"].items():
                if _norm(k) == _norm(table):
                    return rows
            return []
        for k, rows in data.items():
            if _norm(k) == _norm(table) and isinstance(rows, list):
                return rows
    return []


def _all_tables(data):
    if isinstance(data, dict) and isinstance(data.get("tables"), dict):
        return data["tables"]
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if isinstance(v, list)}
    return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--data", required=True, help="grouped {'tables': {...}} database")
    parser.add_argument("--spec", required=True, help="join spec JSON: {table, joins:[...]}")
    parser.add_argument("--out", required=True)
    parser.add_argument("--reachable", action="store_true",
                        help="instead of enriching, print the columns reachable from the base table")
    args = parser.parse_args()

    with open(args.schema, "r", encoding="utf-8") as f:
        schema = json.load(f)
    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(args.spec, "r", encoding="utf-8") as f:
        spec = json.load(f)

    table = spec.get("table")
    if args.reachable:
        rc = [{"table": r["table"], "column": r["column"], "multiplies": r["multiplies"],
               "hops": len(r["path"])} for r in reachable_columns(schema, table)]
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(rc, f, ensure_ascii=False, indent=2)
        print("reachable columns from %s: %d" % (table, len(rc)))
        return

    base_rows = _rows_for_table(data, table)
    rows = enrich(schema, _all_tables(data), table, base_rows, spec.get("joins", []))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print("table=%s  in=%d  out=%d" % (table, len(base_rows), len(rows)))


if __name__ == "__main__":
    main()
