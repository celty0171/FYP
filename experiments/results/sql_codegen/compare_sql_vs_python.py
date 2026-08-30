"""Reference-vs-generated oracle for the SQL builder (Step 0, data layer).

For a battery of selections over Mondial, this asserts that the **pushed-down SQL path**
(``build_selection_sql`` executed against a live PostgreSQL) returns the same rows as the
**offline Python path** (``join.enrich`` -> ``filter.apply`` -> ``aggregate.prepare`` over the
bundled JSON fixture). Equivalence is checked as an order-insensitive multiset over the
columns that matter (selected + brought for a plain selection; group-by/measure aliases for an
aggregate), with numeric values compared under a small tolerance.

This is the same discipline as the Step-1/2/3 codegen comparisons: the reference is the
authoritative offline stage, and the generated program must agree with it. The battery is run
**without** a display ``limit`` — the top-N cut is a deliberately different (measure-desc)
display semantic, not part of the marshalling contract.

Run (needs the ``fyp`` env with SQLAlchemy + a live Mondial on the configured URL)::

    .../envs/fyp/bin/python experiments/results/sql_codegen/compare_sql_vs_python.py

Exit code is non-zero if any case mismatches.
"""

from __future__ import annotations

import json
import math
import os
import sys

_EXP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (_EXP, os.path.dirname(_EXP)):
    if p not in sys.path:
        sys.path.insert(0, p)

from join import join_tables as JOIN            # noqa: E402
from filter import apply_filters as FILTER      # noqa: E402
from aggregate import aggregate_rows as AGG      # noqa: E402
from config import load_config                   # noqa: E402
from results.sql_codegen.build_selection_sql_reference import build_selection_sql  # noqa: E402


# --------------------------------------------------------------------- battery
def _battery(blind_cases):
    cases = []
    # 1) the blind cases — pure projection, exact. economy/lake carry columns the live PG
    #    typed INTEGER (gdp/depth/elevation) vs float in the JSON fixture, so those raw
    #    projections are compared at integer precision (store provenance, not builder logic).
    _int_tables = {"economy", "lake"}
    for c in blind_cases:
        cases.append({"name": "blind_%s" % c["case_id"],
                      "round_int": c["selected_table"] in _int_tables,
                      "sel": {"table": c["selected_table"], "columns": c["selected_columns"]}})
    # 2) row filters
    cases += [
        {"name": "filter_range", "cols": ["country", "year", "population"],
         "sel": {"table": "country_population", "columns": ["country", "year", "population"],
                 "filters": [{"column": "year", "op": "range", "min": 1990, "max": 2010}]}},
        {"name": "filter_in", "cols": ["country", "year", "population"],
         "sel": {"table": "country_population", "columns": ["country", "year", "population"],
                 "filters": [{"column": "country", "op": "in", "values": ["A", "D", "F"]}]}},
        {"name": "filter_gt_notnull", "cols": ["name", "elevation"],
         "sel": {"table": "mountain", "columns": ["name", "elevation"],
                 "filters": [{"column": "elevation", "op": "gt", "value": 4000},
                             {"column": "name", "op": "not_null"}]}},
    ]
    # 3) forward join (bring a parent attribute onto the child) — non-multiplying, exact.
    cases.append({"name": "join_parent_name", "cols": ["country", "population", "country_name"],
                  "sel": {"table": "country_population",
                          "columns": ["country", "population"],
                          "joins": [{"bring": "country.name", "as": "country_name",
                                     "policy": "first"}]}})
    # 4) aggregates
    cases += [
        {"name": "agg_sum_by_country", "cols": ["country", "sum_population"],
         "sel": {"table": "country_population", "columns": ["country", "population"],
                 "aggregate": {"group_by": ["country"],
                               "measures": [{"column": "population", "fn": "sum"}]}}},
        {"name": "agg_resample_decade", "cols": ["decade", "total_population"],
         "sel": {"table": "country_population", "columns": ["year", "population"],
                 "aggregate": {"resample": [{"column": "year", "bucket": 10, "as": "decade"}],
                               "group_by": ["decade"],
                               "measures": [{"column": "population", "fn": "sum",
                                             "as": "total_population"}]}}},
        {"name": "agg_countdistinct", "cols": ["country", "count_distinct_continent"],
         "sel": {"table": "encompasses", "columns": ["country", "continent"],
                 "aggregate": {"group_by": ["country"],
                               "measures": [{"column": "continent", "fn": "count_distinct"}]}}},
        {"name": "agg_having", "cols": ["country", "count"],
         "sel": {"table": "encompasses", "columns": ["country", "continent"],
                 "aggregate": {"group_by": ["country"],
                               "measures": [{"column": "continent", "fn": "count"}],
                               "having": [{"column": "count", "op": "gt", "value": 1}]}}},
    ]
    # 5) group_having filter (keep member rows without collapsing)
    cases.append({"name": "group_having", "cols": ["country", "continent"],
                  "sel": {"table": "encompasses", "columns": ["country", "continent"],
                          "filters": [{"op": "group_having", "group_by": ["country"],
                                       "having": [{"fn": "count_distinct", "column": "continent",
                                                   "op": "gt", "value": 1}]}]}})
    return cases


# --------------------------------------------------------------- normalisation
def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        from decimal import Decimal
        if isinstance(v, Decimal):
            return float(v)
    except Exception:
        pass
    return None


def _cell(v, round_int=False):
    """Canonical comparable value: numbers as rounded floats, everything else as str.

    ``round_int`` compares numbers at integer precision — used only for raw-projection
    cases on columns the live PG typed ``INTEGER`` while the JSON fixture holds floats
    (a store-provenance difference, not a builder difference).
    """
    n = _num(v)
    if n is not None:
        return ("n", float(round(n)) if round_int else round(n, 4))
    if v is None:
        return ("z",)
    return ("s", str(v))


def _multiset(rows, cols, round_int=False):
    ms = {}
    for r in rows:
        key = tuple(_cell(_lookup(r, c), round_int) for c in cols)
        ms[key] = ms.get(key, 0) + 1
    return ms


def _lookup(row, col):
    if col in row:
        return row[col]
    cl = col.lower()
    for k, v in row.items():
        if str(k).lower() == cl:
            return v
    return None


def _cols_for(case, sel):
    if "cols" in case:
        return case["cols"]
    return sel["columns"]


# --------------------------------------------------------------------- run
def python_rows(schema, tables, sel):
    table = sel["table"]
    rows = tables.get(table) or []
    rows = JOIN.enrich(schema, tables, table, rows, sel.get("joins") or [])
    rows = FILTER.apply(rows, sel.get("filters") or [])
    if sel.get("aggregate"):
        _, _, _, rows = AGG.prepare(schema, table, rows, sel["aggregate"])
    return rows


def sql_rows(engine, schema, sel):
    from sqlalchemy import text
    query, params = build_selection_sql(schema, sel)
    with engine.connect() as conn:
        res = conn.execute(text(query), params)
        keys = list(res.keys())
        return [dict(zip(keys, row)) for row in res.fetchall()]


def main():
    cfg = load_config()
    if not cfg.database_url:
        print("no DATABASE_URL / PG_* configured — cannot execute SQL path", file=sys.stderr)
        return 2

    # Source BOTH paths from the live PG so the comparison isolates builder logic from any
    # data-provenance difference (the bundled JSON fixture is a different Mondial snapshot):
    # the SQL path runs in-DB, and the Python path runs over the same rows fetched from PG.
    from datasource.postgres_source import PostgresDataSource
    ds = PostgresDataSource(cfg.database_url, row_cap=cfg.row_cap)
    schema = ds.get_schema()
    tables = {t: ds.get_rows(t) for t in schema["tables"]}
    engine = ds._engine  # reuse the same connection pool

    blind_path = os.path.join(_EXP, "inputs", "mondial_blind_cases.json")
    with open(blind_path, encoding="utf-8") as f:
        blind = json.load(f).get("cases", [])

    cases = _battery(blind)
    passed = failed = 0
    for case in cases:
        sel = case["sel"]
        cols = _cols_for(case, sel)
        ri = bool(case.get("round_int"))
        try:
            py = _multiset(python_rows(schema, tables, sel), cols, ri)
            sq = _multiset(sql_rows(engine, schema, sel), cols, ri)
        except Exception as e:  # noqa: BLE001
            print("ERROR %-22s %s" % (case["name"], e))
            failed += 1
            continue
        if py == sq:
            passed += 1
            print("ok   %-22s rows=%d" % (case["name"], sum(sq.values())))
        else:
            failed += 1
            only_py = {k: v for k, v in py.items() if py[k] != sq.get(k, 0)}
            only_sq = {k: v for k, v in sq.items() if sq[k] != py.get(k, 0)}
            print("FAIL %-22s py=%d sql=%d  (py_only=%d sql_only=%d)" % (
                case["name"], sum(py.values()), sum(sq.values()),
                len(only_py), len(only_sq)))
            for k in list(only_py)[:3]:
                print("       py-only:", k, "x", py[k], "vs sql", sq.get(k, 0))
            for k in list(only_sq)[:3]:
                print("       sql-only:", k, "x", sq[k], "vs py", py.get(k, 0))

    print("\n%d/%d cases agree" % (passed, passed + failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
