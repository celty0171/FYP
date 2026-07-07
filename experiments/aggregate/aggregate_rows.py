"""Phase 1b same-table aggregation — the deterministic *aggregate* prepare stage.

Runs after join+filter: it collapses many rows into one row per group (group-by +
measures, with optional resample bucketing) and emits BOTH the aggregated rows and a
synthetic single-table schema describing them. The aggregated result is a derived
`basic_entity` (group-by columns = key, measures = numeric attributes, no foreign
keys), so the existing Step-1 -> 2 -> 3 pipeline classifies and visualises it with no
change to Step 2/3 or any renderer (see aggregate/PLAN.md).

Standard library only, no gold knowledge (schema + rows only, so the blind/gold
separation invariant is preserved).

Aggregate spec::

    { "table": "country_population",
      "aggregate": {
        "resample":  [ { "column": "year", "bucket": 10, "as": "decade" } ],
        "group_by":  ["continent", "decade"],
        "measures":  [ { "column": "population", "fn": "sum", "as": "total_population" } ]
      } }

Functions: sum, mean (avg), min, max, count, count_distinct. `count` ignores `column`
(counts rows per group); the others coerce via float and skip non-numeric values.
An empty `group_by` is a single global aggregate; an empty/absent spec is the identity.

Run offline::

    python experiments/aggregate/aggregate_rows.py --schema schema.json \
        --data mondial_data.json --spec agg_spec.json --out result.json
"""

from __future__ import annotations

import argparse
import json
import math
from typing import Any

FUNCTIONS = {"sum", "mean", "avg", "min", "max", "count", "count_distinct"}


def _norm(s: Any) -> str:
    return s.lower() if isinstance(s, str) else s


def _row_get(row: dict, column: str):
    if column in row:
        return row[column]
    cn = _norm(column)
    for k, v in row.items():
        if _norm(k) == cn:
            return v
    return None


def _to_number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def _sort_key(values):
    """Deterministic ordering of a group key tuple: numbers first (numerically),
    then strings (alphabetically); None sorts last."""
    key = []
    for v in values:
        if v is None:
            key.append((2, ""))
            continue
        n = _to_number(v)
        if n is not None and not isinstance(v, str):
            key.append((0, n))
        elif n is not None:
            key.append((0, n))  # numeric-looking strings still order numerically
        else:
            key.append((1, str(v)))
    return key


def resample(rows, specs):
    """Add a bucketed column per spec: as = floor(value / bucket) * bucket."""
    if not specs:
        return [dict(r) for r in rows or [] if isinstance(r, dict)]
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        rr = dict(r)
        for spec in specs:
            col = spec.get("column")
            bucket = spec.get("bucket")
            alias = spec.get("as") or (str(col) + "_bucket")
            n = _to_number(_row_get(rr, col)) if col else None
            b = _to_number(bucket)
            if n is None or not b:
                rr[alias] = None
            else:
                rr[alias] = int(math.floor(n / b) * b)
        out.append(rr)
    return out


def _measure_alias(m):
    if m.get("as"):
        return m["as"]
    fn = (m.get("fn") or "sum").lower()
    if fn == "count":
        return "count"
    return fn + "_" + str(m.get("column"))


def _reduce(fn, col, group_rows):
    fn = fn.lower()
    if fn == "count":
        return len(group_rows)
    vals = [_row_get(r, col) for r in group_rows]
    if fn == "count_distinct":
        return len({v for v in vals if v is not None})
    nums = [n for n in (_to_number(v) for v in vals) if n is not None]
    if not nums:
        return None
    if fn == "sum":
        return sum(nums)
    if fn in ("mean", "avg"):
        return sum(nums) / len(nums)
    if fn == "min":
        return min(nums)
    if fn == "max":
        return max(nums)
    return None


def aggregate(rows, group_by, measures):
    """Group `rows` by `group_by` and reduce each `measure`. Deterministic group order.

    Empty `group_by` -> one global row. One output row per group: the group keys plus
    each measure's alias. Never mutates input.
    """
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    group_by = group_by or []
    groups: dict[tuple, list] = {}
    order: list[tuple] = []
    for r in rows:
        key = tuple(_row_get(r, g) for g in group_by)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    if not group_by and not rows:
        # global aggregate of nothing -> a single empty-ish row is unhelpful; return []
        return []

    order.sort(key=_sort_key)
    out = []
    for key in order:
        row = {}
        for i, g in enumerate(group_by):
            row[g] = key[i]
        for m in measures or []:
            row[_measure_alias(m)] = _reduce(m.get("fn") or "sum", m.get("column"), groups[key])
        out.append(row)
    return out


def _source_types(source_schema, table):
    tables = source_schema.get("tables", {}) if isinstance(source_schema, dict) else {}
    for tname, tdef in tables.items():
        if _norm(tname) == _norm(table):
            return {_norm(c.get("name")): c.get("type", "") for c in tdef.get("columns", [])}
    return {}


def _measure_type(fn):
    fn = (fn or "sum").lower()
    if fn in ("count", "count_distinct"):
        return "INTEGER"
    if fn in ("mean", "avg"):
        return "DOUBLE"
    if fn == "sum":
        return "BIGINT"
    return "DOUBLE"  # min / max


def derived_schema(source_schema, table, group_by, measures, bucket_cols=None):
    """Synthetic single-table schema for the aggregated result: group_by = PK,
    measures = numeric attributes, no foreign keys. Returns (schema, table, columns)."""
    bucket_cols = bucket_cols or set()
    src_types = _source_types(source_schema, table)
    dtable = str(table) + "_agg"
    columns = []
    for g in group_by or []:
        if _norm(g) in {_norm(b) for b in bucket_cols}:
            gtype = "INTEGER"
        else:
            gtype = src_types.get(_norm(g), "VARCHAR")
        columns.append({"name": g, "type": gtype})
    dcols = list(group_by or [])
    for m in measures or []:
        alias = _measure_alias(m)
        columns.append({"name": alias, "type": _measure_type(m.get("fn"))})
        dcols.append(alias)
    schema = {"tables": {dtable: {
        "columns": columns,
        "primary_key": list(group_by or []),
        "foreign_keys": [],
    }}}
    return schema, dtable, dcols


def prepare(source_schema, table, rows, aggregate_spec):
    """resample -> aggregate -> synthetic schema. The single call the server uses.

    Returns (derived_schema, derived_table, derived_columns, aggregated_rows).
    """
    spec = aggregate_spec or {}
    resamples = spec.get("resample") or []
    group_by = spec.get("group_by") or []
    measures = spec.get("measures") or []

    rs_rows = resample(rows, resamples)
    agg_rows = aggregate(rs_rows, group_by, measures)
    bucket_cols = {s.get("as") or (str(s.get("column")) + "_bucket") for s in resamples}
    dschema, dtable, dcols = derived_schema(source_schema, table, group_by, measures, bucket_cols)
    return dschema, dtable, dcols, agg_rows


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True, help="source schema summary JSON")
    parser.add_argument("--data", required=True, help="mondial_data.json (grouped) or a row array")
    parser.add_argument("--spec", required=True, help="aggregate spec JSON: {table, aggregate:{...}}")
    parser.add_argument("--out", required=True, help="where to write the aggregated rows")
    parser.add_argument("--schema-out", help="optional: also write the derived synthetic schema")
    args = parser.parse_args()

    with open(args.schema, "r", encoding="utf-8") as f:
        schema = json.load(f)
    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(args.spec, "r", encoding="utf-8") as f:
        spec = json.load(f)

    table = spec.get("table")
    rows = _rows_for_table(data, table)
    dschema, dtable, dcols, agg_rows = prepare(schema, table, rows, spec.get("aggregate", {}))

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(agg_rows, f, ensure_ascii=False, indent=2)
    if args.schema_out:
        with open(args.schema_out, "w", encoding="utf-8") as f:
            json.dump(dschema, f, ensure_ascii=False, indent=2)

    print("table=%s -> derived=%s  in=%d  groups=%d  columns=%s"
          % (table, dtable, len(rows), len(agg_rows), dcols))


if __name__ == "__main__":
    main()
