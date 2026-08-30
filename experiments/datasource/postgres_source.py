"""PostgreSQL data source — reads live schema (PK/FK/types) and rows from a user's
database and emits the exact schema dict + row dicts the pipeline consumes.

Uses SQLAlchemy's ``inspect`` for portable metadata and the psycopg2 driver. Third-party
imports are deferred to construction time so importing this module never breaks the
std-lib experiment path when SQLAlchemy is not installed.

Type strings are normalised to the base names Step 2's ``base_sql_type`` /
``dimension_type`` recognise (VARCHAR / INTEGER / NUMERIC / DATE / TIMESTAMP …); row
values are coerced to JSON-compatible scalars (Decimal -> float/int, date/datetime ->
ISO string) so a live-DB row is indistinguishable from a JSON-file row downstream.
"""

from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import importlib.util
import os
from typing import Any

from .base import DataSource, _is_aggregate

DEFAULT_ROW_CAP = 5000

# Column-name hints that mark a *numeric* column as temporal (mirrors filter.apply_filters).
_TEMPORAL_HINTS = ("year", "date", "time", "timestamp")
_TEMPORAL_TYPES = ("DATE", "TIME", "TIMESTAMP", "YEAR")
_NUMERIC_TYPES = ("INT", "INTEGER", "BIGINT", "SMALLINT", "NUMERIC", "DECIMAL",
                  "FLOAT", "DOUBLE", "REAL", "MONEY", "SERIAL", "BIGSERIAL")


def _load_sql_builder():
    """Load the authoritative LLM-authored SQL builder (results/sql_codegen), the same way
    the server loads its Step-2/3 modules — by file path, so it stays swappable."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.abspath(os.path.join(
        here, "..", "results", "sql_codegen", "build_selection_sql_reference.py"))
    spec = importlib.util.spec_from_file_location("build_selection_sql_reference", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_selection_sql

# Map Postgres/SQLAlchemy type spellings to the base names Step 2 knows.
_TYPE_ALIASES = {
    "CHARACTER VARYING": "VARCHAR",
    "CHARACTER": "CHAR",
    "BPCHAR": "CHAR",
    "DOUBLE PRECISION": "DOUBLE",
    "TIMESTAMP WITHOUT TIME ZONE": "TIMESTAMP",
    "TIMESTAMP WITH TIME ZONE": "TIMESTAMP",
    "TIME WITHOUT TIME ZONE": "TIME",
    "TIME WITH TIME ZONE": "TIME",
}


def _normalise_type(raw: Any) -> str:
    """Uppercase base SQL type name, aliased to what Step 2 recognises."""
    s = str(raw).strip().upper()
    base = s.split("(")[0].strip()  # drop length/precision, e.g. VARCHAR(4) -> VARCHAR
    return _TYPE_ALIASES.get(base, base)


def _find_schema_table(schema: dict, name: str):
    for tname, tdef in (schema.get("tables", {}) or {}).items():
        if str(tname).lower() == str(name).lower():
            return tname, tdef
    return None, None


def _dim_of(name: str, raw_type: Any) -> str:
    """scalar / temporal / discrete from a column's SQL type + name (mirrors filter's dims)."""
    base = _normalise_type(raw_type)
    lname = (name or "").lower()
    if base in _TEMPORAL_TYPES:
        return "temporal"
    if any(base.startswith(t) for t in _NUMERIC_TYPES):
        return "temporal" if any(h in lname for h in _TEMPORAL_HINTS) else "scalar"
    return "discrete"


def _int_if_whole(v: Any) -> Any:
    """Present a whole number as an int so the UI shows clean bounds (matches column_stats)."""
    if isinstance(v, float) and v == int(v):
        return int(v)
    return v


def _coerce(value: Any) -> Any:
    """Make a DB value JSON-compatible so it matches the JSON-file rows exactly."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, _decimal.Decimal):
        # Keep integers integral; everything else becomes a float.
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (_dt.date, _dt.datetime, _dt.time)):
        return value.isoformat()
    return str(value)


class PostgresDataSource(DataSource):
    def __init__(self, url: str, row_cap: int = DEFAULT_ROW_CAP,
                 pushdown: bool = True, statement_timeout_ms: int = 0) -> None:
        try:
            from sqlalchemy import create_engine, inspect  # noqa: F401
        except ImportError as exc:  # pragma: no cover - surfaced at runtime
            raise RuntimeError(
                "PostgresDataSource needs SQLAlchemy + psycopg2 "
                "(pip install -r experiments/requirements.txt)"
            ) from exc
        self._create_engine = create_engine
        self._sa_inspect = inspect
        self._engine = create_engine(url)
        self._row_cap = row_cap
        self._pushdown = pushdown
        self._statement_timeout_ms = max(0, int(statement_timeout_ms or 0))
        self._schema_cache: dict[str, Any] | None = None
        self._build_sql = None  # lazily loaded SQL builder

    # -- schema --------------------------------------------------------------
    def get_schema(self) -> dict[str, Any]:
        if self._schema_cache is not None:
            return self._schema_cache
        insp = self._sa_inspect(self._engine)
        tables: dict[str, Any] = {}
        for tname in insp.get_table_names():
            columns = [
                {
                    "name": c["name"],
                    "type": _normalise_type(c.get("type", "")),
                    "nullable": bool(c.get("nullable", True)),
                }
                for c in insp.get_columns(tname)
            ]
            pk = list(insp.get_pk_constraint(tname).get("constrained_columns") or [])
            fks = [
                {
                    "columns": list(fk.get("constrained_columns") or []),
                    "references_table": fk.get("referred_table", ""),
                    "references_columns": list(fk.get("referred_columns") or []),
                }
                for fk in insp.get_foreign_keys(tname)
            ]
            # UNIQUE constraints are the authoritative signal for alternative keys
            # (chartselect.altkeys); a single-column UNIQUE column can label the entity in
            # place of its primary key. Best-effort: some dialects/reflection paths omit them.
            try:
                uniques = [
                    {"columns": list(uc.get("column_names") or [])}
                    for uc in insp.get_unique_constraints(tname)
                    if uc.get("column_names")
                ]
            except Exception:  # noqa: BLE001 — reflection may not support it; degrade to data-driven
                uniques = []
            tables[tname] = {"columns": columns, "primary_key": pk,
                             "foreign_keys": fks, "unique_constraints": uniques}
        self._schema_cache = {"tables": tables}
        return self._schema_cache

    # -- rows ----------------------------------------------------------------
    def get_rows(self, table: str, limit: int | None = None) -> list[dict[str, Any]]:
        from sqlalchemy import text

        # `table` is validated against the schema before it reaches here (server /
        # nl_to_selection only ever pass known table names); quote it defensively.
        known = set(self.get_schema().get("tables", {}))
        if table not in known:
            return []
        cap = self._row_cap if limit is None else min(limit, self._row_cap)
        stmt = text('SELECT * FROM "' + table.replace('"', '') + '" LIMIT :cap')
        with self._engine.connect() as conn:
            result = conn.execute(stmt, {"cap": cap})
            keys = list(result.keys())
            return [
                {k: _coerce(v) for k, v in zip(keys, row)}
                for row in result.fetchall()
            ]

    # -- pushdown ------------------------------------------------------------
    def _read_only(self, conn) -> None:
        """Make the current transaction read-only and time-bounded (defence for live DBs)."""
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        if self._statement_timeout_ms > 0:
            conn.exec_driver_sql("SET LOCAL statement_timeout = %d" % self._statement_timeout_ms)

    def get_selection(self, table, columns=None, joins=None, filters=None,
                      aggregate=None, limit=None):
        """Push join -> filter -> (aggregate) into one parameterised SQL query (exact over the
        whole table). Falls back to the Python default (``super().get_selection``) when pushdown
        is disabled or on **any** SQL-builder / execution error — graceful degradation."""
        if not self._pushdown:
            return super().get_selection(table, columns, joins, filters, aggregate, limit)
        try:
            from sqlalchemy import text
            schema = self.get_schema()
            if self._build_sql is None:
                self._build_sql = _load_sql_builder()
            # A display top-N always bounded by the hard row-cap ceiling.
            eff_limit = self._row_cap if limit is None else min(int(limit), self._row_cap)
            sel = {"table": table, "columns": list(columns or []), "joins": joins or [],
                   "filters": filters or [], "aggregate": aggregate or {}}
            sql_rows, params_rows = self._build_sql(schema, dict(sel, limit=eff_limit))
            sql_full, params_full = self._build_sql(schema, dict(sel, limit=None))
            count_sql = "SELECT COUNT(*) FROM (%s) _c" % sql_full

            with self._engine.connect() as conn:
                trans = conn.begin()
                try:
                    self._read_only(conn)
                    res = conn.execute(text(sql_rows), params_rows)
                    keys = list(res.keys())
                    rows = [{k: _coerce(v) for k, v in zip(keys, r)} for r in res.fetchall()]
                    rows_total = int(conn.execute(text(count_sql), params_full).scalar() or 0)
                    trans.commit()
                except Exception:
                    trans.rollback()
                    raise

            # Effective schema/table/columns: derived single-table for the aggregate path.
            if _is_aggregate(aggregate):
                dschema, dtable, dcols = self._derived(schema, table, aggregate)
                return {"schema": dschema, "table": dtable, "columns": dcols,
                        "rows": rows, "rows_total": rows_total, "aggregated": True}
            return {"schema": schema, "table": table, "columns": list(columns or []),
                    "rows": rows, "rows_total": rows_total, "aggregated": False}
        except Exception:
            # Any failure in the pushed-down path degrades to the deterministic Python path.
            return super().get_selection(table, columns, joins, filters, aggregate, limit)

    @staticmethod
    def _derived(schema, table, aggregate):
        """Reuse the pure derived-schema builder so the aggregate path matches the offline one."""
        exp = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        import sys as _sys
        if exp not in _sys.path:
            _sys.path.insert(0, exp)
        from aggregate.aggregate_rows import derived_schema
        spec = aggregate or {}
        resamples = spec.get("resample") or []
        bucket_cols = {s.get("as") or (str(s.get("column")) + "_bucket") for s in resamples}
        return derived_schema(schema, table, spec.get("group_by") or [],
                              spec.get("measures") or [], bucket_cols)

    def get_column_stats(self, table, joins=None):
        """Exact per-column filter stats pushed into SQL for the base table (no joins). With
        joins present, degrade to the Python default so joined columns are still covered."""
        if not self._pushdown or joins:
            return super().get_column_stats(table, joins)
        try:
            return self._column_stats_sql(table)
        except Exception:
            return super().get_column_stats(table, joins)

    def _column_stats_sql(self, table):
        from sqlalchemy import text
        from filter.apply_filters import MAX_DISTINCT  # single source of truth for the cap

        schema = self.get_schema()
        _, tdef = _find_schema_table(schema, table)
        if tdef is None:
            return {}
        tq = '"' + str(table).replace('"', '') + '"'
        out: dict[str, Any] = {}
        with self._engine.connect() as conn:
            trans = conn.begin()
            try:
                self._read_only(conn)
                for col in tdef.get("columns", []):
                    name = col.get("name")
                    dim = _dim_of(name, col.get("type", ""))
                    cq = '"' + str(name).replace('"', '') + '"'
                    if dim in ("scalar", "temporal"):
                        row = conn.execute(text(
                            "SELECT COUNT(%s), MIN(%s), MAX(%s) FROM %s" % (cq, cq, cq, tq)
                        )).fetchone()
                        entry: dict[str, Any] = {"dim": dim, "count": int(row[0] or 0)}
                        if row[1] is not None:
                            entry["min"] = _int_if_whole(_coerce(row[1]))
                            entry["max"] = _int_if_whole(_coerce(row[2]))
                        out[name] = entry
                    else:
                        distinct = int(conn.execute(text(
                            "SELECT COUNT(DISTINCT %s) FROM %s" % (cq, tq))).scalar() or 0)
                        entry = {"dim": "discrete", "distinct": distinct}
                        if distinct <= MAX_DISTINCT:
                            vals = [ _coerce(r[0]) for r in conn.execute(text(
                                "SELECT DISTINCT %s FROM %s WHERE %s IS NOT NULL" % (cq, tq, cq)
                            )).fetchall() ]
                            try:
                                entry["values"] = sorted(vals, key=lambda x: (str(type(x)), x))
                            except TypeError:
                                entry["values"] = vals
                        else:
                            entry["high_cardinality"] = True
                        out[name] = entry
                trans.commit()
            except Exception:
                trans.rollback()
                raise
        return out
