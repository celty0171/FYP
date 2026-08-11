"""LLM chart selection over the deterministic Step-2 candidates.

``select(schema, table, columns, pattern, s2, client, rows, intent)`` takes the output of the
deterministic recommender (``s2 = {recommended_charts, candidates, selected}``) and asks an
LLM to choose which eligible candidate best serves the user's goal, justify it in one short
English sentence, rank every candidate with a one-line note, and (optionally) swap a selected
column into an existing mapping role.

It is *intent-aware and data-aware*: when the caller passes the user's original request
(``intent``) and the rows, the prompt carries a distilled goal line plus deterministic
data-shape signals (row count, per-column cardinality / null share / numeric range), so the
same columns under different goals or data scales can lead to different charts.

Guardrails — the LLM never widens what the deterministic layer already allowed:

* It may only pick a chart from the eligible candidates (each already carries a valid
  mapping), so Step 3 always receives a renderable chart.
* A mapping override may only change the *column* that fills an existing role, and only to
  another selected column of the **same dimension** (scalar/temporal/discrete). Mapping keys
  are never added, renamed, or removed, so the Step-2 -> Step-3 field-name contract holds.
* The prompt contains schema evidence + column roles + candidate charts + the user's request
  and measured data signals only — never a gold pattern or expected visualisation — so the
  experiment's blind/gold separation is intact.

Any error, missing key, or invalid answer returns the deterministic pick with
``source="fallback"``; a valid answer returns ``source="llm"``.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

NUMERIC_TYPES = {
    "INT", "INTEGER", "BIGINT", "SMALLINT", "NUMERIC", "DECIMAL",
    "FLOAT", "DOUBLE", "REAL", "MONEY",
}
TEMPORAL_TYPES = {"DATE", "TIME", "TIMESTAMP", "YEAR"}
TEXT_TYPES = {"VARCHAR", "CHAR", "TEXT"}

_SYSTEM = (
    "You are choosing the single most effective visualisation for a data selection, from a "
    "FIXED list of already-valid candidate charts, to serve the user's goal. Output ONLY a "
    "JSON object, no prose.\n\n"
    "Decide from: (a) the user's request/goal if given, (b) each column's type and role, "
    "(c) the measured data signals (a key with hundreds of distinct values makes a bar or "
    "single-axis chart unreadable; two independent scalars suit a scatter; a regular date "
    "series suits a line; few categories suit part-to-whole).\n\n"
    "Rules:\n"
    "- 'recommended_chart' MUST be exactly one of the candidate chart names given.\n"
    "- You may NOT invent charts, mapping keys, or column names.\n"
    "- A chart marked [CONDITIONAL] (e.g. choropleth needs a geographic key; word cloud needs "
    "a lexical/text key) may be chosen ONLY when the user's goal or the column semantics "
    "clearly satisfy its precondition (e.g. the goal mentions a map/geography, or the key "
    "names places). Otherwise prefer an unconditional candidate.\n"
    "- 'mapping_overrides' is optional: an object {role: column} that swaps which selected "
    "column fills an existing role of the chosen chart. Use it when the goal emphasises a "
    "particular column (put it in the lead role). Only use roles listed as swappable for that "
    "chart, and only columns from that role's allowed list (same data dimension).\n"
    "- 'reason' MUST be ONE short English sentence (<= 200 characters) explaining why the "
    "chosen chart reads best for this goal and data.\n"
    "- 'ranking' MUST list EVERY candidate chart, best-first, each as "
    '{"chart": "<name>", "note": "<<=120-char reason it fits or falls short for this goal>"}.\n\n'
    "Output shape:\n"
    "{\n"
    '  "recommended_chart": "<one candidate chart name>",\n'
    '  "mapping_overrides": {"<role>": "<selected column>"},\n'
    '  "reason": "<one short English sentence>",\n'
    '  "ranking": [{"chart": "<name>", "note": "<short reason>"}, ...]\n'
    "}"
)


def _base_sql_type(type_str: Any) -> str:
    if not isinstance(type_str, str):
        return ""
    return type_str.strip().upper().split("(")[0].strip()


def _dim(sql_type: Any) -> str:
    b = _base_sql_type(sql_type)
    if b in NUMERIC_TYPES:
        return "scalar"
    if b in TEMPORAL_TYPES:
        return "temporal"
    if b in TEXT_TYPES:
        return "discrete"
    return "other"


def _column_meta(schema: dict[str, Any], table: str, columns: list[str]) -> dict[str, dict[str, Any]]:
    """Per selected column: {type, dim, is_pk, is_fk} — the pool the LLM may swap within."""
    tdef = schema.get("tables", {}).get(table) or {}
    typemap: dict[str, str] = {}
    for col in tdef.get("columns") or []:
        name = col.get("name") if isinstance(col, dict) else col
        typemap[name] = col.get("type", "") if isinstance(col, dict) else ""
    pk = set(tdef.get("primary_key") or [])
    fk_cols: set[str] = set()
    for fk in tdef.get("foreign_keys") or []:
        for c in fk.get("columns") or []:
            fk_cols.add(c)
    meta: dict[str, dict[str, Any]] = {}
    for c in columns:
        t = typemap.get(c, "")
        meta[c] = {"type": t, "dim": _dim(t), "is_pk": c in pk, "is_fk": c in fk_cols}
    return meta


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def _data_signals(rows: list[dict[str, Any]] | None, columns: list[str],
                  meta: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Deterministic data-shape stats (A3): row count + per-column cardinality / null share /
    numeric range. Grounds the chart choice in real data scale, not just column types."""
    rows = rows or []
    n = len(rows)
    per_col: dict[str, dict[str, Any]] = {}
    for c in columns:
        seen: set[Any] = set()
        nulls = 0
        vmin = vmax = None
        for r in rows:
            v = r.get(c)
            if v is None or v == "":
                nulls += 1
                continue
            seen.add(v)
            if meta.get(c, {}).get("dim") == "scalar":
                fv = _num(v)
                if fv is not None:
                    vmin = fv if vmin is None else min(vmin, fv)
                    vmax = fv if vmax is None else max(vmax, fv)
        info: dict[str, Any] = {
            "distinct": len(seen),
            "null_frac": round(nulls / n, 3) if n else 0.0,
        }
        if vmin is not None:
            info["min"] = vmin
            info["max"] = vmax
        per_col[c] = info
    return {"rows": n, "columns": per_col}


def _signals_text(sig: dict[str, Any]) -> str:
    lines = ["rows=" + str(sig.get("rows", 0))]
    for c, info in (sig.get("columns") or {}).items():
        parts = ["distinct=" + str(info.get("distinct"))]
        if info.get("null_frac"):
            parts.append("null=" + str(info["null_frac"]))
        if "min" in info:
            parts.append("range=" + str(info["min"]) + ".." + str(info["max"]))
        lines.append("  " + c + ": " + ", ".join(parts))
    return "\n".join(lines)


def _swappable_roles(mapping: dict[str, Any], meta: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """For each mapping role whose value is a selected column with same-dimension
    alternatives, list the allowed replacement columns. 'table' and literal values
    (e.g. the string "count") are never swappable."""
    out: dict[str, dict[str, Any]] = {}
    for role, val in mapping.items():
        if role == "table" or val not in meta:
            continue
        dim = meta[val]["dim"]
        options = [c for c, m in meta.items() if m["dim"] == dim and c != val]
        if options:
            out[role] = {"current": val, "dim": dim, "options": options}
    return out


def _eligible_candidates(s2: dict[str, Any]) -> list[dict[str, Any]]:
    """Charts the selector may pick. Includes ``eligible == "conditional"`` charts
    (choropleth / word cloud): they are structurally valid but need a geographic / lexical key
    the schema can't prove — the user's goal can supply that evidence. They stay clearly
    flagged in the prompt, and the deterministic pick + fallback never choose them, so an
    unjustified elevation can only come from an explicit LLM decision."""
    return [
        c for c in s2.get("candidates", [])
        if c.get("eligible") in (True, "conditional")
        and isinstance(c.get("mapping"), dict) and c.get("mapping")
    ]


def _fallback(s2: dict[str, Any], error: str = "") -> dict[str, Any]:
    sel = s2.get("selected") or {}
    charts = s2.get("recommended_charts", [])
    return {
        "recommended_chart": sel.get("chart"),
        "mapping": sel.get("mapping") or {},
        "reason": "",
        "ranking": [{"chart": c, "note": ""} for c in charts],
        "source": "fallback",
        "error": error,
    }


def _build_user_prompt(pattern: str, meta: dict[str, dict[str, Any]],
                       cands: list[dict[str, Any]], signals: dict[str, Any],
                       intent: str) -> str:
    cols_desc = ", ".join(
        c + ":" + m["type"] + "[" + m["dim"]
        + ("/pk" if m["is_pk"] else "") + ("/fk" if m["is_fk"] else "") + "]"
        for c, m in meta.items()
    )
    lines: list[str] = []
    if intent:
        lines.append("User goal: " + intent.strip())
    lines.append("ER pattern: " + str(pattern))
    lines.append("Selected columns: " + cols_desc)
    lines.append("Data signals:")
    lines.append(_signals_text(signals))
    lines.append("")
    lines.append("Candidate charts:")
    for c in cands:
        mapping = c.get("mapping") or {}
        swap = _swappable_roles(mapping, meta)
        cond = " [CONDITIONAL: pick only if the goal/columns satisfy its precondition]" \
            if c.get("eligible") == "conditional" else ""
        lines.append("- " + c["chart"] + cond + ": " + str(c.get("reason", "")))
        lines.append("    mapping: " + json.dumps(mapping, ensure_ascii=False))
        if swap:
            swap_desc = "; ".join(
                r + " (now " + s["current"] + ", " + s["dim"] + ") -> one of "
                + str(s["options"]) for r, s in swap.items()
            )
            lines.append("    swappable roles: " + swap_desc)
        else:
            lines.append("    swappable roles: none")
    lines.append("")
    lines.append("Return the JSON object, ranking EVERY candidate.")
    return "\n".join(lines)


def _apply_overrides(mapping: dict[str, Any], overrides: Any,
                     meta: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Accept only valid same-dimension column swaps into existing roles; ignore the rest."""
    out = deepcopy(mapping)
    if not isinstance(overrides, dict):
        return out
    for role, new_val in overrides.items():
        if role == "table" or role not in out:
            continue
        orig = out[role]
        if orig not in meta or new_val not in meta:
            continue
        if meta[new_val]["dim"] != meta[orig]["dim"]:
            continue
        out[role] = new_val
    return out


def _clean_ranking(raw_ranking: Any, by_chart: dict[str, Any], chart_names: list[str]) -> list[dict[str, str]]:
    """Keep only ranking entries naming a real candidate; append any the model omitted."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_ranking or []:
        if isinstance(item, dict):
            chart, note = item.get("chart"), str(item.get("note") or "")[:120]
        else:
            chart, note = item, ""
        if chart in by_chart and chart not in seen:
            out.append({"chart": chart, "note": note})
            seen.add(chart)
    for c in chart_names:
        if c not in seen:
            out.append({"chart": c, "note": ""})
    return out


def select(schema: dict[str, Any], table: str, columns: list[str], pattern: str,
           s2: dict[str, Any], client: Any = None, step2_model: str | None = None,
           rows: list[dict[str, Any]] | None = None, intent: str = "") -> dict[str, Any]:
    """Rank the Step-2 candidates and pick the one that best serves the user's goal.

    Returns ``{recommended_chart, mapping, reason, ranking, source}`` where ``ranking`` is a
    list of ``{chart, note}``. ``source`` is ``"llm"`` for a valid model answer, else
    ``"fallback"`` (deterministic pick). ``rows`` powers the data-shape signals and ``intent``
    the user-goal line; both are optional. ``client`` may be injected for testing.
    """
    cands = _eligible_candidates(s2)
    if not cands:
        return _fallback(s2, "no eligible candidates")

    chart_names = [c["chart"] for c in cands]
    by_chart = {c["chart"]: c for c in cands}
    meta = _column_meta(schema, table, columns)
    signals = _data_signals(rows, columns, meta)

    if client is None:
        try:
            from config import load_config
            from nlquery.bailian_client import BailianClient

            cfg = load_config()
            client = BailianClient(
                api_key=cfg.dashscope_api_key,
                base_url=cfg.dashscope_base_url,
                model=step2_model or cfg.step2_model,
            )
        except Exception as exc:  # noqa: BLE001 — keep the pipeline alive without an LLM
            return _fallback(s2, "llm client unavailable: " + str(exc))

    user = _build_user_prompt(pattern, meta, cands, signals, intent)
    error = ""
    for attempt in range(2):
        prompt = user if attempt == 0 else (
            user + "\n\nYour previous answer was invalid: " + error
            + "\nChoose recommended_chart from exactly: " + str(chart_names) + " and return valid JSON."
        )
        try:
            raw = client.chat_json(_SYSTEM, prompt)
        except Exception as exc:  # noqa: BLE001
            error = "model did not return parseable JSON: " + str(exc)
            continue
        chart = raw.get("recommended_chart")
        if chart not in by_chart:
            error = "recommended_chart '" + str(chart) + "' is not a candidate"
            continue
        mapping = _apply_overrides(by_chart[chart]["mapping"], raw.get("mapping_overrides"), meta)
        reason = str(raw.get("reason") or "").strip()[:200]
        ranking = _clean_ranking(raw.get("ranking"), by_chart, chart_names)
        return {
            "recommended_chart": chart,
            "mapping": mapping,
            "reason": reason,
            "ranking": ranking,
            "source": "llm",
            "error": "",
        }

    return _fallback(s2, error or "could not select a chart")
