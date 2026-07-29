"""Natural language -> structured selection ``{table, columns, filters, joins, aggregate}``.

The LLM only ever proposes a **data selection** against the schema — it never names a
pattern or a chart, so Step 1 / Step 2 remain the sole (deterministic) deciders and the
experiment's blind/gold separation is untouched. Every table/column the model returns is
validated against the schema; on a violation we retry once with the error, then give up
with a clear message rather than emit a bad selection.
"""

from __future__ import annotations

import json
from typing import Any

ALLOWED_OPS = {"range", "in", "eq", "not_null"}
ALLOWED_AGG_FNS = {"sum", "mean", "avg", "min", "max", "count", "count_distinct"}

_SYSTEM = (
    "You translate a user's natural-language request into a JSON data selection against a "
    "given relational schema. Output ONLY a JSON object, no prose. Never invent table or "
    "column names — use exactly the names in the schema. Do NOT choose a chart type or a "
    "visualisation pattern; only pick data.\n\n"
    "Output shape:\n"
    "{\n"
    '  "table": "<base table name>",\n'
    '  "columns": ["<column>", ...],           // columns of the base table to visualise\n'
    '  "joins": [ {"bring": "<other_table>.<column>", "as": "<alias>", "policy": "first"} ],\n'
    '  "filters": [ {"column": "<col or alias>", "op": "<eq|in|range|not_null>",\n'
    '                "value": <v>, "values": [<v>...], "min": <n>, "max": <n>} ],\n'
    '  "aggregate": {"group_by": ["<col>"...], "measures": [{"column":"<col>","fn":"sum","as":"<alias>"}]}\n'
    "}\n"
    "Rules: omit joins/filters/aggregate if not needed (use [] or {}). For a filter use "
    "only one of value / values / (min,max) matching the op (eq->value, in->values, "
    "range->min&max, not_null->none). To filter by an attribute that lives in another "
    "table (e.g. a country's continent), add a join to bring that column in, then filter "
    "on its alias.\n\n"
    "Example — request: 'borders between South American countries'. The borders table has "
    "country1, country2, length but no continent, so join it in via the country/encompasses "
    "relation and filter on it:\n"
    "{\"table\":\"borders\",\"columns\":[\"country1\",\"country2\",\"length\"],"
    "\"joins\":[{\"bring\":\"encompasses.continent\",\"as\":\"continent\",\"policy\":\"first\"}],"
    "\"filters\":[{\"column\":\"continent\",\"op\":\"in\",\"values\":[\"South America\"]}],"
    "\"aggregate\":{}}"
)


def _schema_brief(schema: dict[str, Any]) -> str:
    """Compact human-readable schema: table(col:TYPE[pk][fk->t.c], ...)."""
    lines = []
    for tname, tdef in schema.get("tables", {}).items():
        pk = set(tdef.get("primary_key") or [])
        fk_map = {}
        for fk in tdef.get("foreign_keys") or []:
            ref_t = fk.get("references_table", "")
            ref_cs = fk.get("references_columns") or []
            for i, c in enumerate(fk.get("columns") or []):
                ref_c = ref_cs[i] if i < len(ref_cs) else ""
                fk_map[c] = ref_t + ("." + ref_c if ref_c else "")
        cols = []
        for col in tdef.get("columns") or []:
            name = col.get("name") if isinstance(col, dict) else col
            typ = col.get("type", "") if isinstance(col, dict) else ""
            tags = ""
            if name in pk:
                tags += " pk"
            if name in fk_map:
                tags += " fk->" + fk_map[name]
            cols.append(name + ":" + str(typ) + tags)
        lines.append(tname + "(" + ", ".join(cols) + ")")
    return "\n".join(lines)


def _columns_of(schema: dict[str, Any], table: str) -> set[str]:
    tdef = schema.get("tables", {}).get(table) or {}
    out = set()
    for col in tdef.get("columns") or []:
        out.add(col.get("name") if isinstance(col, dict) else col)
    return out


def _validate(selection: dict[str, Any], schema: dict[str, Any]) -> str | None:
    """Return an error string if the selection is not schema-valid, else None."""
    table = selection.get("table")
    tables = schema.get("tables", {})
    if not table or table not in tables:
        return "table '" + str(table) + "' is not in the schema"

    base_cols = _columns_of(schema, table)

    # joins bring in <other_table>.<column> aliases
    join_aliases = set()
    for j in selection.get("joins") or []:
        bring = j.get("bring", "")
        if "." not in bring:
            return "join.bring '" + str(bring) + "' must be '<table>.<column>'"
        jt, jc = bring.split(".", 1)
        if jt not in tables:
            return "join table '" + jt + "' is not in the schema"
        if jc not in _columns_of(schema, jt):
            return "join column '" + jc + "' is not in table '" + jt + "'"
        join_aliases.add(j.get("as") or jc)

    known = base_cols | join_aliases
    for c in selection.get("columns") or []:
        if c not in known:
            return "column '" + str(c) + "' is not in table '" + table + "' (or a join)"

    for f in selection.get("filters") or []:
        if f.get("column") not in known:
            return "filter column '" + str(f.get("column")) + "' is not available"
        if f.get("op") not in ALLOWED_OPS:
            return "filter op '" + str(f.get("op")) + "' not in " + str(sorted(ALLOWED_OPS))

    agg = selection.get("aggregate") or {}
    for c in agg.get("group_by") or []:
        if c not in known:
            return "aggregate group_by '" + str(c) + "' is not available"
    for m in agg.get("measures") or []:
        if m.get("column") not in known:
            return "aggregate measure column '" + str(m.get("column")) + "' is not available"
        if m.get("fn") not in ALLOWED_AGG_FNS:
            return "aggregate fn '" + str(m.get("fn")) + "' not in " + str(sorted(ALLOWED_AGG_FNS))
    return None


def _normalise(selection: dict[str, Any]) -> dict[str, Any]:
    """Fill defaults so downstream consumers get the exact expected shape."""
    return {
        "table": selection.get("table"),
        "columns": list(selection.get("columns") or []),
        "joins": list(selection.get("joins") or []),
        "filters": list(selection.get("filters") or []),
        "aggregate": selection.get("aggregate") or {},
    }


def parse(nl_text: str, schema: dict[str, Any], client: Any = None) -> dict[str, Any]:
    """Parse ``nl_text`` into a validated selection.

    Returns ``{"ok": bool, "selection": {...}|None, "error": str, "raw": {...}|None}``.
    ``client`` may be injected (for testing); otherwise a Bailian client is built from
    ``config.load_config()``.
    """
    if client is None:
        from config import load_config
        from nlquery.bailian_client import from_config

        client = from_config(load_config())

    brief = _schema_brief(schema)
    user = "Schema:\n" + brief + "\n\nRequest: " + nl_text.strip() + "\n\nReturn the JSON selection."

    error = ""
    raw: dict[str, Any] | None = None
    for attempt in range(2):
        prompt = user if attempt == 0 else (
            user + "\n\nYour previous answer was invalid: " + error + "\nFix it and return valid JSON."
        )
        try:
            raw = client.chat_json(_SYSTEM, prompt)
        except (json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
            error = "model did not return parseable JSON: " + str(exc)
            continue
        err = _validate(raw, schema)
        if err is None:
            return {"ok": True, "selection": _normalise(raw), "error": "", "raw": raw}
        error = err

    return {"ok": False, "selection": None, "error": error or "could not resolve request", "raw": raw}
