"""Build the configured DataSource. Default is JSON (experiments unchanged)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import DataSource
from .json_source import JsonFileDataSource

if TYPE_CHECKING:  # avoid a runtime cross-module import; annotations are stringised
    from config import Config


def make_datasource(config: "Config") -> DataSource:
    if config.datasource == "postgres":
        if not config.database_url:
            raise RuntimeError(
                "VIZER_DATASOURCE=postgres but no DATABASE_URL / PG_* set in .env"
            )
        from .postgres_source import PostgresDataSource

        return PostgresDataSource(
            config.database_url,
            row_cap=config.row_cap,
            pushdown=getattr(config, "pushdown", True),
            statement_timeout_ms=getattr(config, "statement_timeout_ms", 0),
        )
    # default / "json"
    return JsonFileDataSource(config.schema_path, config.data_path)
