# Towards an intent-aware visualisation agent

Status: **proposal — pending item-by-item confirmation.** Nothing here is built yet; this
document collects the candidate improvements to LLM chart selection (Step 2) and an
architectural assessment of whether that selection should become a standalone sub-agent as
the system grows into a data-visualisation *agent*.

Context: today the Step-2 LLM selector (`experiments/chartselect/llm_chart_selector.py`) is
**intent-blind** — it sees only data structure (table, columns, types/roles, ER pattern,
candidate charts + mappings, and, for many-many, relationship signals). The natural-language
path (`experiments/nlquery/nl_to_selection.py`) deliberately discards the user's original
request after producing a `{table, columns, filters, joins, aggregate}` selection, so the
user's *purpose* never reaches the chart decision. The same columns under different goals
warrant different charts (e.g. "compare GDP across countries" → bar; "GDP vs unemployment
correlation" → scatter), which the current selector cannot distinguish.

Guardrails that every item below must preserve:
- **Blind/gold separation** — the selector may read user *input* (request text, chosen
  columns) but never a gold pattern, expected visualisation, or gold reasoning.
- **Step-2 → Step-3 mapping field-name contract** — mapping keys stay fixed; only
  same-dimension column swaps into existing roles are allowed.
- **Deterministic core** — candidate generation and validation stay deterministic; the LLM
  only ranks/justifies within the validated candidate set, with graceful fallback.

---

## Part A — Improvement backlog (priority order)

### A1. Feed user intent / original NL request to the selector  ⭐ highest value
- **What.** Pass the user's original request (or a distilled one-line "analytical intent")
  from `/api/nl` into `select()` as an extra soft signal in the prompt.
- **Why.** Makes the selector purpose-aware; resolves same-columns/different-goal cases
  (the bar-vs-scatter split behind blind cases 2 and 3).
- **Hook.** `nl_select()` in `server.py` already has the text; thread it through
  `run_pipeline` → `_step2_block` → `select(..., intent=...)`; add an `Intent:` line to
  `_build_user_prompt`.
- **Invariants.** Intact — intent is user input, not gold; candidate set and mapping
  contract unchanged.
- **Feasibility.** High. **Priority 1.**

### A2. Visualisation-task taxonomy (intent as a structured signal)
- **What.** Tag intent into a small vocabulary — `comparison / correlation / distribution /
  trend / part-to-whole / ranking / geospatial / relationship-flow / outlier` (Munzner-style
  task abstraction). Produced either by a light LLM classifier over the NL text or chosen by
  the user from a UI dropdown.
- **Why.** Turns "purpose" into a structured, auditable input the selector can reason from
  (correlation→scatter, trend→line, geospatial→choropleth), and makes evaluation tractable.
- **Hook.** Optional new field on the selection; feeds A1's prompt line. UI dropdown in
  `index.html` next to the run button.
- **Invariants.** Intact (a task label is not a chart/pattern label).
- **Feasibility.** Medium — needs a defined vocabulary and a classification step. **Priority 4.**

### A3. Data-shape signals for *all* patterns (not just many-many)
- **What.** Pre-compute measurable stats per candidate for every pattern: key cardinality
  (|key| ~200 countries makes a bar unreadable → choropleth/word cloud fits better), scalar
  skew/outliers, whether a temporal column is a genuine regular series, number of distinct
  categories, etc.; add them to the prompt.
- **Why.** Grounds "purpose" in real data scale, not just column types — the data+task pair
  is what visualisation theory says should drive the encoding.
- **Hook.** Extend the deterministic measurement style already used by
  `relationship_signals()` in `gpt_recommend_charts.py`; surface via the candidate objects.
- **Invariants.** Intact — purely deterministic pre-computation.
- **Feasibility.** High. **Priority 2.**

### A4. Score-and-explain every candidate (not just pick one)
- **What.** Have the selector return a ranked list with a per-candidate one-line
  fit/anti-fit rationale, not a single pick.
- **Why.** Upgrades the confirm-and-edit UX: the user sees "for your goal, A is best
  because…, B is an alternative for…" and can switch with one click.
- **Hook.** Extend the selector's output schema (ranking already exists) and the
  `#charts`/`#llmRow` rendering in `index.html`.
- **Invariants.** Intact.
- **Feasibility.** High. **Priority 3.**

### A5. Intent-driven mapping fine-tune (reuse the same-dimension swap)
- **What.** When intent emphasises a column ("focus on unemployment"), the selector puts it
  in the primary visual role (measure/y).
- **Why.** Choose not only the right chart but the right column for the lead role.
- **Hook.** The `_apply_overrides` same-dimension swap already supports this; it only needs
  the A1 intent signal to drive it.
- **Invariants.** Intact (mechanism already contract-safe).
- **Feasibility.** High (depends on A1). **Priority 3.**

### A6. Preference feedback loop (longer term)
- **What.** When the user manually switches to a different chart in the UI, log it as a
  preference / few-shot exemplar to improve later prompts.
- **Why.** Continuous, personalised improvement.
- **Hook.** New logging on the `#charts` click handler + a store the prompt can read from.
- **Invariants.** Intact if only chart choices (not gold) are logged.
- **Feasibility.** Medium-low. **Priority 6.**

### Evaluation caveat (applies to A1/A2/A5)
The 9 blind cases' gold `expected_visualisations` implicitly assume one fixed purpose. Once
intent is a variable, an intent-aware selector may *legitimately* diverge from gold, so
"is the pick ∈ gold?" is no longer a fair score for intent-sensitive cases. Plan a small
**intent-conditioned gold set** ("given intent X, the expected chart is Y") before landing
A1, so the current 7/9 rule-vs-LLM comparison is not muddied. Framed well, the need for this
is itself a paper contribution (it demonstrates why intent-awareness matters).

Suggested sequence: **A1 → A3 → A4/A5 → A2 → A6** (A1/A3 are the foundation; A4/A5 are
near-zero-cost wins; A2 needs vocabulary design; A6 is incremental).

---

## Part B — Should Step-2 chart selection be a sub-agent?

**Recommendation: no — keep chart selection as a single constrained LLM *skill* (one
`chat_json` call) invoked by an orchestrator, not a standalone autonomous sub-agent. Promote
it to a sub-agent only when it needs to *iterate on rendered output* or *probe data with its
own tool calls*.**

### Assessment against standard sub-agent criteria

| Criterion | Chart selection today | Verdict |
|---|---|---|
| Multi-step planning needed? | One ranking decision over a small validated candidate set. | No |
| Context-isolation benefit? | Tiny input (one table's columns + a few candidates); nothing to quarantine from a main context. | No |
| Tool use / autonomy / "when am I done"? | None today; a single call in, a JSON out. | No (today) |
| Reusability across contexts? | Called once per run, in one place. | Low |
| Latency / cost budget? | Runs on every UI selection; one call ≪ an agent loop. | Favours single call |
| Reproducibility / gold-evaluability? | Constrained single call is far easier to score than an autonomous loop. | Favours single call |

A sub-agent (its own planning loop, tools, and stop condition) is overkill for a bounded
rank-and-justify task. The value we already get comes precisely from *constraining* the LLM
to deterministic candidates — an autonomous agent would work against that.

### The right framing: one agent, several skills/tools

Treat the whole system as a single **VizAgent orchestrator** that sequences:
- deterministic **tools** — Step 1 classify, Step 2 candidate generation, Step 3 render,
  data-source queries;
- LLM **skills** (single constrained calls) — intent understanding (NL→selection + A2 task
  label), chart selection (Step 2 LLM), each with schema validation + fallback.

In this model, Step-2 LLM selection is a *skill the orchestrator calls*, not a peer agent
with its own goals. This keeps the LLM-as-compiler discipline (deterministic spine, LLM at
well-defined seams) while making the system feel agentic end-to-end.

### When promotion to a genuine sub-agent *is* justified

A separate sub-agent earns its keep only when the subtask becomes genuinely agentic — i.e.
it must loop, use tools, and decide when it is done. The natural candidate is **not** chart
selection in isolation but a **"critique-and-refine" sub-agent** that owns Steps 2+3 together:

1. pick a chart (the current skill),
2. render it (Step 3 tool),
3. inspect the result for visual defects (overplotting, too many categories, an unreadable
   200-bar axis, empty encodings),
4. re-pick or adjust the mapping,
5. stop when the rendered result passes.

Promote to a sub-agent when any of these hold:
- **Iterative visual critique** is wanted (generate → render → inspect → refine loop).
- The selector must **probe the data itself** (run its own aggregate/cardinality queries via
  the data-source tool) before deciding, rather than being handed pre-computed signals (A3).
- **Ambiguous intent** should trigger an interactive **clarifying question** to the user.

Until one of those is on the table, a single constrained call is the correct design.

### Recommended near-term step

Refactor the current call behind a small **skill interface** (e.g. `VizSkill.select_chart`)
with a typed input (schema-selection + intent + signals) and validated output, so the
orchestrator can call it uniformly and it can later be lifted into a critique-and-refine
sub-agent without changing its callers. No behaviour change now; it just sets up the agent
architecture cleanly.
