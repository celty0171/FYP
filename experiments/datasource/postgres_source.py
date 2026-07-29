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
from typing import Any

from .base import DataSource

DEFAULT_ROW_CAP = 5000

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
    def __init__(self, url: str, row_cap: int = DEFAULT_ROW_CAP) -> None:
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
        self._schema_cache: dict[str, Any] | None = None

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
            tables[tname] = {"columns": columns, "primary_key": pk, "foreign_keys": fks}
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
