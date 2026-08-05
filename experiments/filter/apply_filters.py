"""Phase 1 same-table row filtering — the deterministic *prepare* stage.

Sits between "load the relation's rows" and Step 2 of the pipeline: it takes the
chosen relation's rows and a filter spec and returns the matching subset, so the
Step-2 selector measures density/N on the subset and the Step-3 renderer draws it
(see filter/PLAN.md). Renderers are untouched — the caller wraps the result as
``{"tables": {table: rows}}`` and hands it to each renderer's ``_rows_for``.

Standard library only, no schema/gold knowledge (operates purely on rows, so the
blind/gold separation invariant is preserved).

Filter spec::

    { "table": "country_population",
      "filters": [
        { "column": "year",      "op": "range", "min": 1990, "max": 2020 },
        { "column": "continent", "op": "in",    "values": ["Europe", "Asia"] }
      ] }

Operators (all conjunctive — a row must satisfy every filter):
  range  scalar/temporal  min <= value <= max  (either bound optional)
  in     discrete         value is in `values`
  eq     any              sugar for `in` with one value
  not_null any            drop rows whose column is null/absent
  gt/ge/lt/le  numeric    value >, >=, <, <= `value` (used e.g. for HAVING on an
                          aggregated measure such as count_distinct > 1)

Run offline::

    python experiments/filter/apply_filters.py --data mondial_data.json \
        --spec filter_spec.json --out rows.json
"""

from __future__ import annotations

import argparse
import json
from typing import Any

# Discrete columns list their distinct values only up to this cardinality; above it
# the UI cannot show a checklist, so `column_stats` flags it high-cardinality instead.
MAX_DISTINCT = 60

# Column-name hints that mark a *numeric* column as temporal (both use a range control,
# so this only affects the `dim` label the UI shows).
TEMPORAL_HINTS = ("year", "date", "time", "timestamp")


def _norm(s: Any) -> str:
    return s.lower() if isinstance(s, str) else s


def _row_get(row: dict, column: str):
    """Case-insensitive column lookup; returns (found, value)."""
    if column in row:
        return True, row[column]
    cn = _norm(column)
    for k, v in row.items():
        if _norm(k) == cn:
            return True, v
    return False, None


def _to_number(v):
    """Coerce to float for range comparisons; None if not numeric."""
    if isinstance(v, bool):  # bool is an int subclass — never a measure here
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def _match_range(value, spec) -> bool:
    x = _to_number(value)
    if x is None:
        return False
    lo = spec.get("min")
    hi = spec.get("max")
    if lo is not None:
        lo_n = _to_number(lo)
        if lo_n is not None and x < lo_n:
            return False
    if hi is not None:
        hi_n = _to_number(hi)
        if hi_n is not None and x > hi_n:
            return False
    return True


def _match_cmp(op, value, target) -> bool:
    """Numeric comparison for the gt/ge/lt/le operators; False if either side is
    non-numeric (so a bad spec drops rows rather than matching everything)."""
    x = _to_number(value)
    t = _to_number(target)
    if x is None or t is None:
        return False
    if op == "gt":
        return x > t
    if op == "ge":
        return x >= t
    if op == "lt":
        return x < t
    if op == "le":
        return x <= t
    return False


def _cmp(op, value, target) -> bool:
    """Numeric comparison for gt/ge/lt/le/eq; False if either side is non-numeric."""
    x = _to_number(value)
    t = _to_number(target)
    if x is None or t is None:
        return False
    return {"gt": x > t, "ge": x >= t, "lt": x < t, "le": x <= t, "eq": x == t}.get(op, False)


def _group_reduce(fn, column, group_rows):
    """Aggregate one group's rows for a group_having condition. Mirrors the reducers in
    aggregate/aggregate_rows.py, kept local so the filter stage has no import coupling."""
    fn = (fn or "count").lower()
    if fn == "count":
        return len(group_rows)
    vals = []
    for r in group_rows:
        found, v = _row_get(r, column)
        if found:
            vals.append(v)
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


def _apply_group_having(rows, spec):
    """Keep the ROWS whose group satisfies a per-group aggregate condition (SQL:
    ``WHERE key IN (SELECT key ... GROUP BY key HAVING <cond>)``).

    Unlike aggregate.having this does NOT collapse rows — it only removes rows whose
    group fails the condition, so the selection's visualisation schema pattern (e.g.
    many-many) is preserved and only the data is narrowed. Spec::

        { "op": "group_having", "group_by": ["country"],
          "having": [ {"fn": "count_distinct", "column": "continent",
                       "op": "gt", "value": 1} ] }
    """
    group_by = spec.get("group_by") or []
    having = spec.get("having") or []
    if not group_by or not having:
        return rows

    def key_of(r):
        return tuple(_row_get(r, g)[1] for g in group_by)

    groups: dict[tuple, list] = {}
    for r in rows:
        if isinstance(r, dict):
            groups.setdefault(key_of(r), []).append(r)

    passing = set()
    for key, grp in groups.items():
        ok = True
        for h in having:
            val = _group_reduce(h.get("fn"), h.get("column"), grp)
            if val is None or not _cmp((h.get("op") or "").lower(), val, h.get("value")):
                ok = False
                break
        if ok:
            passing.add(key)
    return [r for r in rows if isinstance(r, dict) and key_of(r) in passing]


def _match_in(value, values) -> bool:
    if not isinstance(values, list):
        return False
    # Compare both raw and stringified so a JSON spec of "1990" matches an int 1990.
    if value in values:
        return True
    sval = str(value)
    return any(sval == str(v) for v in values)


def _row_matches(row: dict, spec: dict) -> bool:
    op = (spec.get("op") or "").strip().lower()
    column = spec.get("column")
    if not column:
        return True  # malformed filter: treat as no-op
    found, value = _row_get(row, column)

    if op == "not_null":
        return found and value is not None
    # Every other operator requires the column to be present and non-null.
    if not found or value is None:
        return False
    if op == "range":
        return _match_range(value, spec)
    if op == "in":
        return _match_in(value, spec.get("values"))
    if op == "eq":
        target = spec.get("value")
        return _match_in(value, [target])
    if op in ("gt", "ge", "lt", "le"):
        return _match_cmp(op, value, spec.get("value"))
    # Unknown operator -> ignore this filter (forward-compatible), so it matches.
    return True


def apply(rows, filters):
    """Return the subset of `rows` satisfying every filter (conjunctive).

    An empty/absent `filters` list is the identity. Never mutates input rows and
    preserves their order. Two filter kinds are supported: ordinary row predicates
    (range/in/eq/not_null/gt/ge/lt/le) and ``group_having`` group-membership filters,
    which keep only rows whose group passes a per-group aggregate condition without
    collapsing the rows (so the visualisation schema pattern is preserved).
    """
    if not filters:
        return list(rows) if rows is not None else []
    active = [f for f in filters if isinstance(f, dict)]
    if not active:
        return list(rows)
    row_filters = [f for f in active if (f.get("op") or "").strip().lower() != "group_having"]
    group_filters = [f for f in active if (f.get("op") or "").strip().lower() == "group_having"]
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if all(_row_matches(r, f) for f in row_filters):
            out.append(r)
    for gf in group_filters:
        out = _apply_group_having(out, gf)
    return out


def _infer_dim(column: str, values) -> str:
    """scalar / temporal / discrete from observed non-null values."""
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "discrete"
    numeric = all(_to_number(v) is not None for v in non_null)
    if numeric:
        cn = _norm(column) or ""
        if any(h in cn for h in TEMPORAL_HINTS):
            return "temporal"
        return "scalar"
    return "discrete"


def column_stats(rows, columns=None):
    """Per-column metadata so the UI can build the right filter control from data.

    scalar/temporal columns report min/max/count; discrete columns list distinct
    values up to MAX_DISTINCT (else `high_cardinality`).
    """
    rows = rows or []
    if columns is None:
        seen: list[str] = []
        seen_set = set()
        for r in rows:
            if isinstance(r, dict):
                for k in r.keys():
                    if k not in seen_set:
                        seen_set.add(k)
                        seen.append(k)
        columns = seen

    out: dict[str, Any] = {}
    for col in columns:
        vals = []
        for r in rows:
            if isinstance(r, dict):
                found, v = _row_get(r, col)
                if found:
                    vals.append(v)
        dim = _infer_dim(col, vals)
        non_null = [v for v in vals if v is not None]
        if dim in ("scalar", "temporal"):
            nums = [n for n in (_to_number(v) for v in non_null) if n is not None]
            entry: dict[str, Any] = {"dim": dim, "count": len(nums)}
            if nums:
                lo, hi = min(nums), max(nums)
                # Present integers as ints so the UI shows clean bounds.
                entry["min"] = int(lo) if lo == int(lo) else lo
                entry["max"] = int(hi) if hi == int(hi) else hi
            out[col] = entry
        else:
            distinct = []
            distinct_set = set()
            for v in non_null:
                if v not in distinct_set:
                    distinct_set.add(v)
                    distinct.append(v)
            entry = {"dim": "discrete", "distinct": len(distinct)}
            if len(distinct) <= MAX_DISTINCT:
                try:
                    entry["values"] = sorted(distinct, key=lambda x: (str(type(x)), x))
                except TypeError:
                    entry["values"] = distinct
            else:
                entry["high_cardinality"] = True
            out[col] = entry
    return out


def _rows_for_table(data, table):
    """Pull a table's rows from a grouped {'tables': {...}} db, a flat map, or a list."""
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
    parser.add_argument("--data", required=True, help="mondial_data.json (grouped) or a row array")
    parser.add_argument("--spec", required=True, help="filter spec JSON: {table, filters:[...]}")
    parser.add_argument("--out", required=True, help="where to write the filtered row array")
    parser.add_argument("--stats", action="store_true",
                        help="also print column_stats for the (unfiltered) table to stderr")
    args = parser.parse_args()

    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(args.spec, "r", encoding="utf-8") as f:
        spec = json.load(f)

    table = spec.get("table")
    rows = _rows_for_table(data, table)
    filtered = apply(rows, spec.get("filters", []))

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(filtered, f, ensure_ascii=False, indent=2)

    if args.stats:
        import sys
        json.dump(column_stats(rows), sys.stderr, ensure_ascii=False, indent=2)
        sys.stderr.write("\n")

    print("table=%s  in=%d  out=%d" % (table, len(rows), len(filtered)))


if __name__ == "__main__":
    main()
