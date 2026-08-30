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

import os
import sys
from abc import ABC, abstractmethod
from typing import Any


def _offline_stages():
    """Lazily import the std-lib join/filter/aggregate stages (single source of truth for
    the Python marshalling path). Kept out of module import so ``base`` stays cheap."""
    exp = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # experiments/
    if exp not in sys.path:
        sys.path.insert(0, exp)
    from join import join_tables as JOIN
    from filter import apply_filters as FILTER
    from aggregate import aggregate_rows as AGG
    return JOIN, FILTER, AGG


def _is_aggregate(spec: dict | None) -> bool:
    return bool(spec and (spec.get("group_by") or spec.get("measures") or spec.get("resample")))


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

    def get_selection(self, table: str, columns: list[str] | None = None,
                      joins: list[dict] | None = None, filters: list[dict] | None = None,
                      aggregate: dict | None = None,
                      limit: int | None = None) -> dict[str, Any]:
        """Join -> filter -> (aggregate) a selection, returning a ``SelectionResult`` dict::

            {"schema", "table", "columns", "rows", "rows_total", "aggregated"}

        The ``schema``/``table``/``columns`` are the *effective* ones the pipeline should feed
        Step 1/2/3 — the base ones for a plain selection, or the derived single-table
        aggregate ones when aggregating. ``rows`` is capped to ``limit``; ``rows_total`` is the
        full count before that cap (for the "showing N / M" badge).

        This default runs the offline Python stages over ``tables_view()`` — it is the exact
        behaviour of the JSON fixture path and the graceful-degradation fallback for any source
        that cannot (or is configured not to) push the work into the backing store.
        """
        JOIN, FILTER, AGG = _offline_stages()
        schema = self.get_schema()
        tables = self.tables_view()
        rows = tables.get(table) or []
        rows = JOIN.enrich(schema, tables, table, rows, joins or [])
        rows = FILTER.apply(rows, filters or [])
        eff_schema, eff_table, eff_cols, aggregated = schema, table, list(columns or []), False
        if _is_aggregate(aggregate):
            eff_schema, eff_table, eff_cols, rows = AGG.prepare(schema, table, rows, aggregate)
            aggregated = True
        rows_total = len(rows)
        if limit is not None:
            rows = rows[:limit]
        return {"schema": eff_schema, "table": eff_table, "columns": eff_cols,
                "rows": rows, "rows_total": rows_total, "aggregated": aggregated}

    def get_column_stats(self, table: str, joins: list[dict] | None = None) -> dict[str, Any]:
        """Per-column filter metadata (dim / min / max / distinct / values) for the base
        table enriched with any joins. Default computes it in Python over ``tables_view()``;
        a live source may override to push MIN/MAX/COUNT(DISTINCT) into the store."""
        JOIN, FILTER, _ = _offline_stages()
        schema = self.get_schema()
        tables = self.tables_view()
        rows = tables.get(table) or []
        rows = JOIN.enrich(schema, tables, table, rows, joins or [])
        return FILTER.column_stats(rows)


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
