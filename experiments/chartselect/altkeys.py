"""Alternative-key (candidate-key) detection — generic to any database.

Definition
----------
Every table has one **primary key**: the identifier the schema designates. An
**alternative key** (a.k.a. candidate / secondary key) is any *other* minimal set of
columns that *also* uniquely identifies every row — one that could equally have been
chosen as the primary key. This module detects **single-column** alternative keys: a
lone non-primary-key column whose values are present (never null/blank) and all-distinct
across the table, so it can stand in for the primary key wherever the entity is
*identified or labelled*. In Mondial ``country.code`` is the primary key and
``country.name`` is an alternative key — both name a country uniquely, so a chart's
identity/label role (a word-cloud word, a choropleth region, a bar-chart key) can plot
either, and the user should be free to switch between them at render time.

Detection is evidence-based and needs no configuration, so it works on a user's own
database:

1. **Schema UNIQUE constraints** — when the data source exposes them (the authoritative
   database signal), a single-column UNIQUE constraint *is* an alternative key.
2. **The data itself** — otherwise, a non-primary-key column with no null/blank value and
   as many distinct values as there are rows is an empirical candidate key. (Empirical:
   it holds for the rows seen; ``MIN_ROWS`` guards against declaring a key from a handful
   of rows.)

Std-lib only, so the experiment core stays importable without any third-party package.
"""

from __future__ import annotations

from typing import Any

# Below this row count an all-distinct column is more likely a coincidence than a genuine
# key, so empirical (data-driven) detection abstains. Schema UNIQUE constraints are trusted
# regardless of row count.
MIN_ROWS = 5

# Continuous real-valued measures: a float/decimal quantity that happens to be all-distinct
# (an area, a latitude) is a coincidence, never a designed identifier, so empirical detection
# ignores these. Integer and text columns can be genuine keys (ids, codes, names) and stay
# eligible. A *declared* UNIQUE constraint overrides this — it is trusted whatever the type.
_CONTINUOUS_TYPES = {"NUMERIC", "DECIMAL", "FLOAT", "DOUBLE", "REAL", "MONEY"}


def _base_type(type_str: Any) -> str:
    return str(type_str or "").strip().upper().split("(")[0].strip()


def _table_def(schema: dict[str, Any], table: str) -> dict[str, Any]:
    return (schema.get("tables", {}) or {}).get(table) or {}


def _column_names(tdef: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for c in tdef.get("columns") or []:
        out.append(c.get("name") if isinstance(c, dict) else c)
    return out


def _declared_unique_singletons(tdef: dict[str, Any]) -> set[str]:
    """Single-column UNIQUE constraints the data source exposed, if any (schema signal)."""
    out: set[str] = set()
    for uc in tdef.get("unique_constraints") or []:
        cols = uc.get("columns") if isinstance(uc, dict) else uc
        if isinstance(cols, list) and len(cols) == 1:
            out.add(cols[0])
        elif isinstance(cols, str):
            out.add(cols)
    return out


def _is_empirical_key(rows: list[dict[str, Any]], col: str, min_rows: int) -> bool:
    """True when ``col`` is non-null and all-distinct across ``rows`` (a candidate key for
    the data seen). A key admits no null/blank value and no duplicate."""
    n = len(rows)
    if n < min_rows:
        return False
    seen: set[Any] = set()
    for r in rows:
        if not isinstance(r, dict):
            return False
        v = r.get(col)
        if v is None or (isinstance(v, str) and not v.strip()):
            return False            # a key cannot be null/blank
        if v in seen:
            return False            # duplicate -> not unique
        seen.add(v)
    return len(seen) == n


def single_column_alternative_keys(schema: dict[str, Any], table: str,
                                   rows: list[dict[str, Any]] | None = None,
                                   *, min_rows: int = MIN_ROWS) -> list[str]:
    """Single-column alternative keys of ``table``, in schema-column order.

    A column qualifies when it is **not** part of the primary key and is either declared
    UNIQUE by the schema or is empirically non-null-and-distinct across ``rows``. Pass the
    table's ``rows`` (as the pipeline already has them) to enable data-driven detection;
    without rows only schema-declared UNIQUE columns are returned.
    """
    tdef = _table_def(schema, table)
    pk = set(tdef.get("primary_key") or [])
    declared = _declared_unique_singletons(tdef)
    types = {(c.get("name") if isinstance(c, dict) else c):
             (c.get("type") if isinstance(c, dict) else "") for c in tdef.get("columns") or []}
    rows = rows or []
    out: list[str] = []
    for name in _column_names(tdef):
        if name in pk:
            continue                # the chosen key, not an *alternative*
        if name in declared:        # schema UNIQUE is authoritative, any type
            out.append(name)
            continue
        if _base_type(types.get(name)) in _CONTINUOUS_TYPES:
            continue                # a coincidentally-unique measure is not a real key
        if _is_empirical_key(rows, name, min_rows):
            out.append(name)
    return out


def _main() -> None:
    """CLI: report each table's primary key and detected alternative keys for the active
    data source (``.env``: JSON files by default, or a live PostgreSQL database). Run:

        python experiments/chartselect/altkeys.py            # every table
        python experiments/chartselect/altkeys.py country    # one table
    """
    import sys
    from pathlib import Path

    exp = Path(__file__).resolve().parents[1]      # experiments/
    if str(exp) not in sys.path:
        sys.path.insert(0, str(exp))
    from config import load_config
    from datasource import make_datasource

    ds = make_datasource(load_config())
    schema = ds.get_schema()
    tables = ds.tables_view()
    only = sys.argv[1] if len(sys.argv) > 1 else None
    names = [only] if only else sorted(schema.get("tables", {}))
    for t in names:
        tdef = schema.get("tables", {}).get(t)
        if not tdef:
            print(t + ": unknown table")
            continue
        pk = tdef.get("primary_key") or []
        alt = single_column_alternative_keys(schema, t, tables.get(t) or [])
        print(t + ":")
        print("  primary key      : " + (", ".join(pk) or "(none)"))
        print("  alternative keys : " + (", ".join(alt) or "(none)"))


if __name__ == "__main__":
    _main()
