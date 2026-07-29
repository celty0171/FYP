"""Natural-language front end: turn a free-text request into the structured selection
``{table, columns, filters, joins, aggregate}`` the existing pipeline already consumes.

This is the one runtime-LLM stage (Bailian / DashScope, OpenAI-compatible). It emits only
a data selection — never a pattern label or chart choice — so the blind/gold separation of
the experiment is preserved.
"""

from .nl_to_selection import parse

__all__ = ["parse"]
