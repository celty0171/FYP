"""JSON-file data source — the default; wraps today's two offline files exactly so the
experiment path is byte-for-byte unchanged.

* schema  = ``mondial_schema_summary_clean.json`` (the clean schema dict)
* data    = ``mondial_data.json`` grouped as ``{"tables": {table: [rows]}}``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import DataSource


class JsonFileDataSource(DataSource):
    def __init__(self, schema_path: str | Path, data_path: str | Path) -> None:
        self._schema = json.loads(Path(schema_path).read_text("utf-8"))
        data = json.loads(Path(data_path).read_text("utf-8"))
        # Accept either the grouped {"tables": {...}} form or a bare {table: rows} dict.
        self._tables: dict[str, list[dict[str, Any]]] = (
            data.get("tables", data) if isinstance(data, dict) else {}
        )

    def get_schema(self) -> dict[str, Any]:
        return self._schema

    def get_rows(self, table: str, limit: int | None = None) -> list[dict[str, Any]]:
        rows = self._tables.get(table) or []
        return rows[:limit] if limit is not None else rows

    def tables_view(self):
        # The whole store is already in memory as a plain dict — hand it over directly
        # (identical to the pre-adapter `DATA["tables"]`).
        return self._tables
