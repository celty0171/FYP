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
    # Unknown operator -> ignore this filter (forward-compatible), so it matches.
    return True


def apply(rows, filters):
    """Return the subset of `rows` satisfying every filter (conjunctive).

    An empty/absent `filters` list is the identity. Never mutates input rows and
    preserves their order.
    """
    if not filters:
        return list(rows) if rows is not None else []
    active = [f for f in filters if isinstance(f, dict)]
    if not active:
        return list(rows)
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if all(_row_matches(r, f) for f in active):
            out.append(r)
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
