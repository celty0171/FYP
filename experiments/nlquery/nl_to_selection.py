"""Natural language -> structured selection ``{table, columns, filters, joins, aggregate}``.

The LLM only ever proposes a **data selection** against the schema — it never names a
pattern or a chart, so Step 1 / Step 2 remain the sole (deterministic) deciders and the
experiment's blind/gold separation is untouched. Every table/column the model returns is
validated against the schema; on a violation we retry once with the error, then give up
with a clear message rather than emit a bad selection.
"""

from __future__ import annotations

import json
import re
from typing import Any

ALLOWED_OPS = {"range", "in", "eq", "not_null", "gt", "ge", "lt", "le", "group_having"}
ALLOWED_AGG_FNS = {"sum", "mean", "avg", "min", "max", "count", "count_distinct"}
# Comparison operators usable inside a having / group_having condition.
CMP_OPS = {"gt", "ge", "lt", "le", "eq"}

_SYSTEM = (
    "You translate a user's natural-language request into a JSON data selection against a "
    "given relational schema. Output ONLY a JSON object, no prose. Never invent table or "
    "column names — use exactly the names in the schema. Do NOT choose a chart type or a "
    "visualisation pattern; only pick data.\n"
    "Choose the table that CONTAINS the attributes to be visualised. If the entity named and "
    "its attributes live in different tables (e.g. GDP/unemployment are in 'economy', not "
    "'country'), pick the table that has the attributes (it is usually keyed by the entity), "
    "or join them in — do not silently drop a requested attribute.\n\n"
    "Output shape:\n"
    "{\n"
    '  "table": "<base table name>",\n'
    '  "columns": ["<column>", ...],           // columns of the base table to visualise\n'
    '  "joins": [ {"bring": "<other_table>.<column>", "as": "<alias>", "policy": "first"} ],\n'
    '  "filters": [ {"column": "<col or alias>", "op": "<eq|in|range|not_null|gt|ge|lt|le>",\n'
    '                "value": <v>, "values": [<v>...], "min": <n>, "max": <n>},\n'
    '               {"op":"group_having","group_by":["<col>"...],\n'
    '                "having":[{"fn":"count_distinct","column":"<col>","op":"<gt|ge|lt|le|eq>","value":<n>}]} ],\n'
    '  "aggregate": {"group_by": ["<col>"...], "measures": [{"column":"<col>","fn":"sum","as":"<alias>"}],\n'
    '                "having": [{"column":"<measure alias or group_by col>","op":"<gt|ge|lt|le|eq>","value":<n>}]}\n'
    "}\n"
    "Rules: for a data-first visualisation, 'columns' MUST include the base table's "
    "identifying key (its primary-key column(s)) as well as the attributes to show — the key "
    "identifies the entities being visualised (e.g. for country include 'code', not only "
    "'name'). Omit joins/filters/aggregate if not needed (use [] or {}). For a plain filter "
    "use only one of value / values / (min,max) matching the op (eq->value, in->values, "
    "range->min&max, not_null->none, gt/ge/lt/le->value). To filter by an attribute that "
    "lives in another table (e.g. a country's continent), add a join to bring that column "
    "in, then filter on its alias.\n"
    "A condition on a COUNT or other per-group aggregate (e.g. 'more than 1 continent', "
    "'at least 3 airports') CANNOT be a plain filter. Choose by intent:\n"
    "  (a) The user still wants to SEE the entities/relationship, just restricted to those "
    "that meet the count — use a group_having FILTER. It keeps the matching rows and does "
    "NOT change what is being visualised. THIS IS THE DEFAULT for 'show/visualise X that "
    "have >N ...'.\n"
    "  (b) The user wants the aggregated NUMBER itself as the chart (e.g. 'how many "
    "continents each country has', 'total population per continent') — use aggregate."
    "group_by + measures (+ having).\n"
    "Use count_distinct to count distinct values, count to count rows.\n\n"
    "Example 1 — request: 'borders between South American countries'. The borders table has "
    "country1, country2, length but no continent, so join it in via the country/encompasses "
    "relation and filter on it:\n"
    "{\"table\":\"borders\",\"columns\":[\"country1\",\"country2\",\"length\"],"
    "\"joins\":[{\"bring\":\"encompasses.continent\",\"as\":\"continent\",\"policy\":\"first\"}],"
    "\"filters\":[{\"column\":\"continent\",\"op\":\"in\",\"values\":[\"South America\"]}],"
    "\"aggregate\":{}}\n"
    "Example 2 — request: 'visualise all countries spanning more than 1 continent'. The user "
    "wants to see these countries and their continents (a country-continent relationship), "
    "just narrowed to the qualifying ones. Keep the encompasses relationship and use a "
    "group_having filter — do NOT aggregate:\n"
    "{\"table\":\"encompasses\",\"columns\":[\"country\",\"continent\"],\"joins\":[],"
    "\"filters\":[{\"op\":\"group_having\",\"group_by\":[\"country\"],"
    "\"having\":[{\"fn\":\"count_distinct\",\"column\":\"continent\",\"op\":\"gt\",\"value\":1}]}],"
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
        op = f.get("op")
        if op == "group_having":
            # Group-membership filter: keeps rows whose group passes a per-group count,
            # without collapsing them (so the pattern is preserved). Validate its own shape.
            gb = f.get("group_by") or []
            if not gb:
                return "group_having needs a non-empty group_by"
            for c in gb:
                if c not in known:
                    return "group_having group_by '" + str(c) + "' is not available"
            for h in f.get("having") or []:
                if h.get("fn") not in ALLOWED_AGG_FNS:
                    return "group_having fn '" + str(h.get("fn")) + "' not in " + str(sorted(ALLOWED_AGG_FNS))
                if (h.get("fn") or "").lower() != "count" and h.get("column") not in known:
                    return "group_having column '" + str(h.get("column")) + "' is not available"
                if h.get("op") not in CMP_OPS:
                    return "group_having op '" + str(h.get("op")) + "' not in " + str(sorted(CMP_OPS))
            continue
        if f.get("column") not in known:
            return "filter column '" + str(f.get("column")) + "' is not available"
        if op not in ALLOWED_OPS:
            return "filter op '" + str(op) + "' not in " + str(sorted(ALLOWED_OPS))

    agg = selection.get("aggregate") or {}
    for c in agg.get("group_by") or []:
        if c not in known:
            return "aggregate group_by '" + str(c) + "' is not available"
    measure_aliases = set()
    for m in agg.get("measures") or []:
        if m.get("column") not in known:
            return "aggregate measure column '" + str(m.get("column")) + "' is not available"
        if m.get("fn") not in ALLOWED_AGG_FNS:
            return "aggregate fn '" + str(m.get("fn")) + "' not in " + str(sorted(ALLOWED_AGG_FNS))
        measure_aliases.add(m.get("as") or ((m.get("fn") or "sum") + "_" + str(m.get("column"))))

    # HAVING runs after aggregation, so its columns are the group-by columns or a
    # measure alias — never a raw base column that was collapsed away.
    having_known = set(agg.get("group_by") or []) | measure_aliases
    for h in agg.get("having") or []:
        if not (agg.get("group_by") or agg.get("measures")):
            return "aggregate having needs a group_by/measures aggregate to filter"
        if h.get("column") not in having_known:
            return "having column '" + str(h.get("column")) + "' must be a group_by column or measure alias"
        if h.get("op") not in ALLOWED_OPS:
            return "having op '" + str(h.get("op")) + "' not in " + str(sorted(ALLOWED_OPS))
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


def _ensure_identifying_columns(selection: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Guarantee a non-aggregate data-first selection carries its identifying key.

    Models often pick readable attributes but drop the primary key, leaving Step 2 with no
    key/region/text role and therefore no candidates. Deterministically prepend any missing
    base-table primary-key column(s). No-op when aggregating (the group_by becomes the key
    downstream) — the added columns are real base columns, so the selection stays valid.
    """
    if selection.get("aggregate"):
        return selection
    tdef = schema.get("tables", {}).get(selection.get("table")) or {}
    pk = tdef.get("primary_key") or []
    cols = list(selection.get("columns") or [])
    missing = [c for c in pk if c not in cols]
    if missing:
        selection["columns"] = missing + cols
    return selection


# --- Deterministic request grounding (no LLM) -------------------------------
# A cheap, reproducible keyword resolver that spots which *measure* columns (numeric/
# temporal attributes) the request literally names, and where they live. It does NOT parse
# the request — the LLM still does the semantic/relational work; this only nudges the model
# towards the right table (a hint) and catches the LLM's known failure of silently dropping a
# named measure (a coverage check + retry). It is high-precision but low-recall: paraphrases
# with no matching keyword ("wealthiest nations") yield nothing, and the LLM is on its own.
_NUMERIC_TYPES = {"INT", "INTEGER", "BIGINT", "SMALLINT", "NUMERIC", "DECIMAL",
                  "FLOAT", "DOUBLE", "REAL", "MONEY"}
_TEMPORAL_TYPES = {"DATE", "TIME", "TIMESTAMP", "YEAR"}
_REQ_STOP = {
    "the", "a", "an", "of", "and", "or", "to", "by", "for", "in", "on", "with", "as", "at",
    "each", "all", "every", "show", "compare", "visualise", "visualize", "display", "plot",
    "how", "what", "which", "who", "where", "across", "between", "their", "its", "me", "i",
    "want", "see", "per", "over", "total", "number", "count", "many", "much", "has", "have",
    "is", "are", "do", "does", "relate", "relates", "related", "relationship", "change",
    "changed", "changes", "this", "that", "these", "those", "list", "give", "find",
}


def _is_measure(type_str: Any) -> bool:
    b = str(type_str or "").strip().upper().split("(")[0].strip()
    return b in _NUMERIC_TYPES or b in _TEMPORAL_TYPES


def _measure_index(schema: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    """Lowercased measure-column name -> [(table, column), ...] over the whole schema."""
    idx: dict[str, list[tuple[str, str]]] = {}
    for t, tdef in (schema.get("tables") or {}).items():
        for col in tdef.get("columns") or []:
            name = col.get("name") if isinstance(col, dict) else col
            typ = col.get("type", "") if isinstance(col, dict) else ""
            if name and _is_measure(typ):
                idx.setdefault(str(name).lower(), []).append((t, str(name)))
    return idx


def resolve_request_columns(text: str, schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Measure columns the request literally names: [{"term", "matches": [(table, col)...]}].

    Deterministic: split into tokens, drop stop-words, and exact-match (with a light plural
    fold) against numeric/temporal column names. Discrete keys (name/code/country) are ignored
    as ubiquitous noise; the point is the *measures* that pin the table and that get dropped.
    """
    idx = _measure_index(schema)
    toks = [w for w in re.split(r"[^a-z0-9]+", (text or "").lower()) if w and w not in _REQ_STOP]
    resolved: dict[str, list[tuple[str, str]]] = {}
    for w in toks:
        for cand in (w, w[:-1] if len(w) > 3 and w.endswith("s") else None):
            if cand and cand in idx and cand not in resolved:
                resolved[cand] = idx[cand]
    return [{"term": k, "matches": v} for k, v in resolved.items()]


def _request_hint(resolved: list[dict[str, Any]]) -> str:
    if not resolved:
        return ""
    parts = []
    for r in resolved:
        tables = sorted({t for t, _ in r["matches"]})
        parts.append(r["matches"][0][1] + " (in " + "/".join(tables[:3]) + ")")
    return ("Attributes the request appears to name: " + "; ".join(parts)
            + ". Choose the table that contains the attributes to visualise, or join them in.")


def _coverage_gap(selection: dict[str, Any], resolved: list[dict[str, Any]]) -> str:
    """Measure terms the request named but the selection omitted (comma-joined), else ""."""
    if not resolved:
        return ""
    present = {str(c).lower() for c in (selection.get("columns") or [])}
    for j in selection.get("joins") or []:
        bring = j.get("bring", "")
        if "." in bring:
            present.add(bring.split(".", 1)[1].lower())
        if j.get("as"):
            present.add(str(j["as"]).lower())
    agg = selection.get("aggregate") or {}
    for m in agg.get("measures") or []:
        if m.get("column"):
            present.add(str(m["column"]).lower())
    for gb in agg.get("group_by") or []:
        present.add(str(gb).lower())
    return ", ".join(r["term"] for r in resolved if r["term"] not in present)


def parse(nl_text: str, schema: dict[str, Any], client: Any = None) -> dict[str, Any]:
    """Parse ``nl_text`` into a validated selection.

    Returns ``{"ok": bool, "selection": {...}|None, "error": str, "raw": {...}|None}``.
    ``client`` may be injected (for testing); otherwise a Bailian client is built from
    ``config.load_config()``. A deterministic keyword resolver adds a table hint and, if the
    model drops a measure the request named, retries once with a correction before accepting.
    """
    if client is None:
        from config import load_config
        from nlquery.bailian_client import from_config

        client = from_config(load_config())

    brief = _schema_brief(schema)
    resolved = resolve_request_columns(nl_text, schema)
    hint = _request_hint(resolved)
    user = ("Schema:\n" + brief + "\n\nRequest: " + nl_text.strip()
            + (("\n\n" + hint) if hint else "") + "\n\nReturn the JSON selection.")

    error = ""
    raw: dict[str, Any] | None = None
    for attempt in range(3):
        prompt = user if not error else (
            user + "\n\nYour previous answer had a problem: " + error + "\nFix it and return valid JSON."
        )
        try:
            raw = client.chat_json(_SYSTEM, prompt)
        except (json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
            error = "model did not return parseable JSON: " + str(exc)
            continue
        err = _validate(raw, schema)
        if err is not None:
            error = err
            continue
        sel = _ensure_identifying_columns(_normalise(raw), schema)
        gap = _coverage_gap(sel, resolved)
        if gap and attempt < 2:  # measure dropped -> correct and retry; accept on the last try
            error = ("the request names " + gap + " but the selection omitted them; choose the "
                     "table that contains them or join them in")
            continue
        return {"ok": True, "selection": sel, "error": "", "raw": raw}

    return {"ok": False, "selection": None, "error": error or "could not resolve request", "raw": raw}
