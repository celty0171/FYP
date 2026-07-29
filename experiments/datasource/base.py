"""DataSource interface + a lazy table view.

A ``DataSource`` yields exactly the two shapes the pipeline already consumes:

* ``get_schema()`` -> the clean schema dict
  ``{"tables": {t: {"columns":[{"name","type","nullable"}], "primary_key":[...],
     "foreign_keys":[{"columns","references_table","references_columns"}]}}}``
* ``get_rows(table)`` -> ``list[dict]`` (one ``{column: value}`` dict per row).

``tables_view()`` returns a mapping ``{table: rows}`` supporting ``.get(table, default)``,
which is all ``join.join_tables.enrich`` needs — so joins work unchanged whether rows come
from a JSON file (a plain dict) or a live DB (the lazy, caching view below).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DataSource(ABC):
    """Produces the pipeline's schema dict and row lists from some backing store."""

    @abstractmethod
    def get_schema(self) -> dict[str, Any]:
        """Return the clean schema dict consumed by Step 1 / Step 2."""

    @abstractmethod
    def get_rows(self, table: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Return the rows of ``table`` as ``{column: value}`` dicts."""

    def tables_view(self) -> "LazyTables":
        """A ``{table: rows}`` mapping (``.get`` only) for ``join_tables.enrich``."""
        return LazyTables(self)


class LazyTables:
    """A minimal ``{table: rows}`` mapping that fetches (and caches) rows on demand.

    ``join_tables.enrich`` accesses the table store only via ``.get(table, default)``, so
    this is the whole surface we need. For a JSON source the store is already a full dict
    in memory; for a live DB this avoids loading every table up front — only the tables on
    a join's FK path are ever fetched.
    """

    def __init__(self, source: DataSource) -> None:
        self._source = source
        self._cache: dict[str, list[dict[str, Any]]] = {}

    def get(self, table: str, default: Any = None) -> Any:
        if table not in self._cache:
            try:
                self._cache[table] = self._source.get_rows(table)
            except Exception:
                return default
        return self._cache[table]

    def __getitem__(self, table: str) -> list[dict[str, Any]]:
        rows = self.get(table)
        if rows is None:
            raise KeyError(table)
        return rows

    def __contains__(self, table: str) -> bool:
        return self.get(table) is not None
