# Step 2 — LLM chart selection prompt

This documents the prompt used by the **opt-in** LLM chart selector that sits on top of the
deterministic Step-2 recommender. The runnable source of truth is
`experiments/chartselect/llm_chart_selector.py` (the `_SYSTEM` constant and
`_build_user_prompt`); this file describes the contract so it can be reviewed and versioned
alongside the other prompts.

## Where it sits

`results/step2_codegen/gpt_recommend_charts.py::recommend()` already emits every eligible
chart **and a valid mapping** for the selection. The selector does **not** replace that — it
asks an LLM only to:

1. pick which eligible candidate to **highlight** (`recommended_chart`);
2. give **one short English sentence** of rationale (`reason`);
3. **rank every candidate** with a one-line note (`ranking`);
4. optionally **swap a column into an existing mapping role** (`mapping_overrides`).

It is **intent-aware and data-aware**: the caller may pass the user's original request
(`intent`) and the selection's rows, so the prompt carries a *User goal* line and
deterministic *Data signals* (row count, per-column cardinality / null share / numeric
range). The same columns under different goals or data scales can then lead to different
charts. Intent is user *input*, not a gold label, so the blind/gold separation still holds.

It is gated by `VIZER_LLM_STEP2` (default `off`) and needs `DASHSCOPE_API_KEY`. On any error,
missing key, or invalid answer it falls back to the deterministic pick (`source="fallback"`).

## Invariants preserved

- **Blind / gold separation** — the prompt carries schema evidence (column names, types,
  pk/fk roles), the ER pattern, and the candidate chart names/mappings only. It never sees a
  gold pattern or an expected visualisation.
- **Step-2 → Step-3 field-name contract** — mapping *keys* are fixed. An override may only
  change which selected **column** fills an existing role, and only to another selected column
  of the **same dimension** (scalar / temporal / discrete). `table` and literal values (e.g.
  the string `"count"`) are never swappable. Invalid overrides are silently ignored.
- **Determinism when off** — with `VIZER_LLM_STEP2=off` (or no key) the experiment path is
  byte-identical to the pure-deterministic Step 2.

## System prompt

```
You are choosing the single most effective visualisation for a data selection, from a FIXED
list of already-valid candidate charts. Output ONLY a JSON object, no prose.

Rules:
- 'recommended_chart' MUST be exactly one of the candidate chart names given.
- You may NOT invent charts, mapping keys, or column names.
- 'mapping_overrides' is optional: an object {role: column} that swaps which selected column
  fills an existing role of the chosen chart. Only use roles listed as swappable for that
  chart, and only columns from that role's allowed list (same data dimension).
- 'reason' MUST be ONE short English sentence (<= 200 characters) explaining, from the column
  types and relationship signals, why this chart reads best for this selection.
- 'ranking' is optional: the candidate chart names best-first.

Output shape:
{
  "recommended_chart": "<one candidate chart name>",
  "mapping_overrides": {"<role>": "<selected column>"},
  "reason": "<one short English sentence>",
  "ranking": ["<chart>", ...]
}
```

## User message shape

```
User goal: <the user's original request>        # omitted when no intent is supplied
ER pattern: <pattern>
Selected columns: <col:TYPE[dim/pk/fk], ...>
Data signals:
rows=<N>
  <col>: distinct=<d>, null=<f>, range=<min>..<max>
  ...

Candidate charts:
- <chart>: <why the deterministic layer marked it eligible>
    mapping: <JSON mapping the renderer will read>
    swappable roles: <role (now <col>, <dim>) -> one of [<cols>]; ...  | none>
...

Return the JSON object, ranking EVERY candidate.
```

## Response contract

```jsonc
{
  "recommended_chart": "scatter diagram",          // must be one of the candidates
  "mapping_overrides": {"y": "unemployment"},       // optional, same-dimension swaps only
  "reason": "Two independent scalar attributes read best as a scatter for a correlation goal.",
  "ranking": [                                      // every candidate, best-first
    {"chart": "scatter diagram", "note": "shows the gdp–unemployment correlation the goal asks for"},
    {"chart": "bar chart", "note": "only compares a single measure across the key"}
  ]
}
```

The server merges this into `step2` as
`llm = {recommended_chart, reason, source, ranking}` and sets `selected` to the highlighted
chart + (possibly overridden) mapping; the full candidate list is still returned so the UI
can show every valid chart with the LLM's pick highlighted.
