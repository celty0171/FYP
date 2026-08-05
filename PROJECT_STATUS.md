# Project Status

## Current Stage

Date: 2026-06-23

The project has moved to an **"LLM-as-compiler"** paradigm (supervisor direction): rather than asking a
model to answer each case at run time (non-deterministic, context-window bound), the model is used
once to **author deterministic programs** for each pipeline step, which then run reproducibly. All
three steps now exist as such programs with aligned contracts, plus a deterministic web front-end that
chains them — see *Work — 2026-06-23* below.

The project is currently at the stage of testing whether LLMs can accurately identify visualisation schema patterns and then implement visually effective web-based visualisations.

LLM access is now automated and multi-model. Self-hosted Qwen models run on the Imperial HPC (cx3) under vLLM with OpenAI-compatible APIs, reached over SSH tunnels: `Qwen3-14B` on `localhost:8001` (best for Stage 1+2) and `Qwen2.5-Coder-32B-Instruct` on `localhost:8004` (best for Stage 3 code generation). An end-to-end pipeline (`experiments/scripts/run_pipeline.py`) drives the models through all three stages without manual web chat; manual web chat (GPT / Claude on the university agent platform) remains a fallback when the HPC models are unavailable.

An interactive web front-end (`experiments/web/`) now exposes all three stages: select a table and columns, run Stage 1+2 (Qwen3-14B), then Stage 3 (Coder-32B → Google Charts) and render the result inline.

## Current Experimental Workflow

The current workflow has three main steps:

1. Pattern identification
   - The LLM is given a selected Mondial table name and column names.
   - It identifies the ER visualisation schema pattern, such as `basic_entity`, `weak_entity`, `one_many_relationship`, `many_many_relationship`, or `reflexive_many_many_relationship`.

2. Chart selection and mapping
   - The LLM uses the visualisation rules from McBrien and Poulovassilis's work to select suitable chart types for the identified schema pattern.
   - It must also produce an explicit entity-to-chart mapping, such as source, target, weight, key, measure, x/y attributes, or size attributes.

3. Visualisation implementation
   - The LLM is given the selected mapping and the relevant Mondial data.
   - It generates a runnable visualisation implementation, currently as standalone HTML files using libraries such as D3 or Google Charts.

For steps 1 and 2, the LLM is given:

- `experiments/pattern_notes.md`
- `experiments/mondial_database/mondial_schema_summary_clean.json`
- `experiments/prompts/mondial_pattern_prompt.md`

For step 3, the LLM is given:

- `experiments/prompts/visualisation_implementation_prompt.md`
- relevant Mondial data JSON files, such as `mondial_data.json`, `mondial_encompasses_data.json`, or `mondial_country_area.json`

## Recent Repository Updates

The dissertation folder now includes the interim report:

- `dissertation/interim_report.pdf`

The literature folder now includes key background sources:

- Hannan 2024 VizER report
- McBrien and Poulovassilis paper on visualisation based on conceptual modelling and schema transformations

A project description file has also been added:

- `project description.md`

## Work — 2026-08-05

Front-end usability + query-expressiveness pass on the deterministic pipeline, plus the Step-2
write-up in the report. No change to Step 1 or the blind/gold separation.

- **Post-aggregate HAVING.** New numeric comparison ops `gt/ge/lt/le` in `filter/apply_filters.py`;
  `aggregate/aggregate_rows.py::prepare` gained a `having` stage (`resample → aggregate → having`,
  reusing the filter engine). Lets "how many X per Y > n" queries be expressed. Wired through the NL
  parser (prompt + `ALLOWED_OPS` + validation) and the manual UI's Aggregate panel.
- **`group_having` filter — keep the relationship, just narrow it.** A group-membership filter
  (`filter/apply_filters.py`) that drops rows whose group fails a per-group count **without
  collapsing** them, so the ER pattern is preserved (e.g. "countries spanning >1 continent" stays
  `many_many`, rendered as a matrix/chord over the qualifying 5 countries, instead of aggregating
  into a `basic_entity` count). Exposed in the manual UI via a "filter entities by this condition"
  toggle (default = raw relationship; ticked = filtered) and in the NL parser (prompt example +
  validation). Verified end-to-end on `encompasses`.
- **NL confirm-and-edit interaction** (`web_pipeline/index.html`). After parsing, the system now
  restates the selection in plain English and lets the user edit it (live-updating summary,
  Confirm/Reset) before it runs — the restatement is derived deterministically from the selection,
  so it always matches what executes.
- **Step-2 relationship recommendation tweaks** (`results/step2_codegen/gpt_recommend_charts.py`):
  the node-link view is now pattern-specific — **Sankey only** for many_many (chord dropped),
  **chord only** for reflexive (Sankey dropped) — and it **leads over the matrix** whenever a scalar
  width is present (matrix leads only when there is no scalar). Old dense/large downgrade of node-link
  removed.
- **Readable labels at render** (`web_pipeline/server.py::apply_display_labels`): display-only swap of
  entity codes for their `name` (e.g. `R → Russia`) in label roles (key/source/target/parent/child/
  region/…), keeping internal codes for all logic. This also fixed a **pre-existing choropleth bug**:
  the renderer joins the basemap by country *name* but Step 2 supplied the *code* as `region`, so every
  feature missed and rendered blank — relabelling `region` to the name fixes the colouring (residual:
  a few Mondial names differ from the world-atlas names and stay grey).
- **Report** (`final_report.tex`): Step 2 rewritten with per-chart/mapping detail, paper-style summary
  tables (booktabs), and bullet lists; Step 3 aligned. Also adds `experiments/metrics/` (relationship
  layout-overlap metrics) to the tree.

## Work — 2026-07-01

Implemented **proposal v2** (`experiments/relationship_viz_proposal_v2_charts_and_selector.md`) §7
"first build" for the two many-many patterns, **without touching Step 1**:

- **Three new Step-3 renderers**, each on the layered `base_d3v7.md` prompt + a new `chart_<x>.md`:
  `viz_codegen_matrix` (adjacency-matrix heatmap — square-symmetric for reflexive, bipartite for
  many_many), `viz_codegen_force` (force-directed graph), `viz_codegen_arc` (arc diagram, **reflexive
  only**). All read `mapping["value"]` = a scalar column **or** the literal `"count"`, so — via the
  **count fallback** — they render the two relations that produced nothing before: `is_member` (no
  scalar, categorical `type`) and `merges_with` (no attribute). Validated on all four Mondial relations
  (see each cell's `SUMMARY.md`): complete HTML, D3 v7, no forbidden APIs.
- **A data-driven Step-2 relationship selector** (proposal §4) in `gpt_recommend_charts.py`: measures
  `density`, `N`, `symmetric` from the rows and ranks charts by an ordered rule table. Result on
  Mondial — `borders` (sparse, scalar) → chord/Sankey-led; `encompasses`/`is_member` (dense/large) →
  **matrix**-led; `merges_with` (attribute-free) → **matrix**-led. Thresholds `DENSE=0.10`,
  `LARGE_N=200`, `SYMMETRIC_MIN=0.6`. New prompt `step2_chart_mapping_prompt_v4.md`; the schema-only
  `recommend_charts_reference.py` sibling gained the new charts (no density ranking).
- **Web front-end** (`web_pipeline/server.py`) registers the three renderers and now passes the
  selected table's rows into Step 2 so the selector is live end-to-end.

Out of scope (future work, noted in the proposal): parallel sets / alluvial, hierarchical edge
bundling, directed-reflexive handling.

## Work — 2026-06-23

Milestone: the whole pipeline is now realised as **deterministic, LLM-authored programs** (Step 1 →
Step 2 → Step 3) with contracts that line up end-to-end, driven by a model-free web front-end. The
shift is from "LLM as per-case executor" to "LLM as compiler": the model writes the program once
(reviewable, testable), and the program runs deterministically thereafter. This dissolves the two
Stage-3 failure axes from the 16k-vs-32k study — the *context-budget* axis disappears (data is read at
run time, never inlined in the prompt) and the *library-version* axis is pinned once per renderer.

Step 1 — pattern identification as a program:

- `experiments/prompts/prompt_v9.md` reworks prompt_v8's Step-1 half to *emit a Python classifier*
  with a fixed `classify_selection` + `--schema/--cases/--out` contract.
- Reference (`results/prompt_v9_codegen/classifier_generated.py`) and GPT
  (`results/prompt_v9_codegen/gpt_generated.py`) both score **9/9** vs the hand-written rule baseline on
  the nine blind cases. Qwen3-14B reached 8/9, then 9/9 after the inherited-key wording was tightened.

Step 2 — chart recommendation + mapping as a program:

- `experiments/prompts/step2_chart_mapping_prompt.md` asks for a deterministic program that types each
  attribute from its SQL type, checks each chart's mandatory requirements (pattern_notes + McBrien &
  Poulovassilis), and emits a mapping whose field names are **exactly** what the Step-3 renderers read.
- Reference (`results/step2_codegen/recommend_charts_reference.py`) and GPT
  (`results/step2_codegen/gpt_recommend_charts.py`) reproduce the expected recommendation + mapping for
  all nine cases; each selected mapping fed straight into its Step-3 renderer rendered a complete HTML
  with **zero glue**. Provenance note: GPT authored a near-correct program one-shot; Qwen3-14B reached
  only 4/9 (parameterised-type parsing, inherited-key alias) and responded non-monotonically to prompt
  edits — complex steps need a strong code model or a reference as the trusted artifact.

Step 3 — visualisation as parameterised renderers (D3 v7), one chart block per chart on a shared base:

- Layered prompts in `experiments/prompts/viz_codegen/` (`base_d3v7.md` + `chart_<x>.md`); the base
  pins D3 v7, forbids brace-based templating, requires interactivity, and reads data from the grouped
  `mondial_data.json` via `mapping["table"]`.
- Renderers built and validated for **all five patterns / 13 charts**:
  `basic_entity` → bar, scatter, bubble, calendar, choropleth, word cloud
  (`results/viz_codegen_{bar,scatterbubble,calendar,choropleth,wordcloud}/`);
  `weak_entity` → line, stacked bar, spider (`results/viz_codegen_weak/`);
  `one_many` → tree map, circle packing (`results/viz_codegen_{treemap,circlepack}/`);
  `many_many` → Sankey (`results/viz_codegen_sankey_d3/`, with a deterministic Step A–C overlap-reduction
  ordering that drops avoidable link crossings to zero on `encompasses`);
  `reflexive_many_many` → chord (`results/viz_codegen_chord/`). Each renders the full Mondial data with
  hover interaction; choropleth/word cloud pull geometry/layout from official CDNs. Only `grouped bar`
  and `hierarchy tree` remain unbuilt (optional).

Deterministic web front-end:

- `experiments/web/` (the Qwen-backed one) is superseded for this purpose by `experiments/web_pipeline/`
  (`server.py` + `index.html`, standard library, **no model calls**): pick a table + columns → Step 1
  `gpt_generated.py` → Step 2 `gpt_recommend_charts.py` → Step 3 `render_*_reference.py`, rendering the
  chosen chart in a sandboxed iframe. Charts without a renderer return the literal `working in process`;
  conditional charts (choropleth / word cloud) appear as "(if geo/lexical)" pills.

Key cross-cutting findings (full detail in each run dir's `SUMMARY.md`):

- Prompt hardening is **non-monotonic** for complex programs on a weak model (Qwen Step-2 v2 fixed two
  bugs but regressed eligibility gating) — captured as evidence, not patched away.
- Authoring difficulty scales with embedded-JS volume: adding interactivity pushed Qwen past the
  f-string/`.format()` brace-collision threshold, which the base now forbids.
- Structural checks are necessary-but-not-sufficient (a renderer can pass them yet be browser-broken);
  static-JS checks were added.

## Work — 2026-06-16

Refocused on Stage 3 (visualisation implementation): ran a controlled two-model comparison on
case8, settled on a Stage 3 configuration, and built an interactive web front-end for all three
stages.

Stage 3 model comparison (case8 = `encompasses`, many_many → Sankey):

- Added `experiments/scripts/run_viz_stage3.py`: a Stage-3-only runner that feeds a *fixed*,
  already-validated Stage 1+2 mapping to the model, so the comparison isolates implementation
  ability rather than re-confounding it with each model's own pattern reasoning.
- Compared `Qwen3-14B` (thinking on) vs `Qwen2.5-Coder-32B-Instruct` (no thinking) across `d3`
  and `google_charts`. Full results and analysis in `experiments/results/viz_case8/COMPARISON.md`.
- Key findings:
  - The binding constraint is the **16384-token context window**, not raw model skill. d3's
    verbose inline JSON plus a long thinking trace do not co-fit: with full data Qwen3-14B's HTML
    is truncated mid-array; with compact data its `<think>` never closes and reasoning leaks in.
  - **Thinking mode is a liability for Stage 3** — the opposite of Stage 1+2. Long HTML output
    competes with the thinking trace for tokens. See memory note `stage3-thinking-liability`.
  - **google_charts is more robust than d3** under a tight context (compact Sankey rows fit all
    251 data rows). Both google_charts outputs completed; Coder-32B's was best (complete + titled).
  - Coder-32B's d3 used `d3.keys()` (removed in d3 v6+) against a v7 CDN. A follow-up with a
    version-constrained d3 prompt (`prompts/visualisation_implementation_prompt_d3v7.md`) confirmed
    this is a **prompt-steerable version/knowledge issue** (all deprecated APIs disappeared), but a
    separate **graph-construction error remains** (`d3.group` returns a Map used as an array;
    continent nodes never built; `nodeId` unset) — a genuine implementation-reasoning gap, not
    version drift. Run: `experiments/results/viz_case8/coder_32b_d3_v7`.

16k-vs-32k context check (Qwen3-14B): a second Qwen3-14B instance was deployed at
`--max-model-len 32768` (separate vLLM server on port 8011, single L40S; the 16k instance on 8001
untouched) and Stage 3 was re-run with thinking on, everything else fixed. Result confirms the
context diagnosis and separates two independent failure axes:

- **d3 + thinking is rescued on completeness.** At 16k it truncated mid-array (175/251 rows, no
  `</html>`); at 32k it is complete — all 251 rows inlined, no thinking leak, titled (445 s).
- **But the d3 version/API bug is unchanged.** The 32k d3 file still pairs `d3-sankey.v1` with
  `d3.v7` and uses the deprecated `sankey.link()` / `.layout()` — the same knowledge/version issue
  as Coder-32B (§4–§5), orthogonal to context size. A bigger window lets the model finish writing
  the wrong API; it does not correct it.
- **google_charts barely changes** (complete, 251 rows, still omits `<title>`) — it already fit at
  16k, so it is the control showing 32k helps only the context-bound path.

So Stage-3 failures decompose into a *context-budget* axis (truncation / `<think>`-leak /
data-stubbing — scales away 16k→32k) and a *library-version/graph-construction* axis (does not
respond to context; remains prompt-work). Runs: `experiments/results/viz_case8_32k/`; full write-up
in `COMPARISON.md` §7.

Chosen Stage 3 configuration: **Coder-32B (thinking off) + google_charts**. (32k removes d3's
completeness risk but the output still needs a version-constrained prompt to be runnable, so the
recommendation is unchanged.)

Added a Stage 3 rubric: `experiments/rubrics/viz_implementation_rubric.md` (runnability, mapping
fidelity, data completeness, chart faithfulness, readability, code quality; 0–2 each).

Interactive web front-end (`experiments/web/`, standard-library only, reuses `run_pipeline.py`):

- `server.py` (ThreadingHTTPServer + urllib) with `/api/schema`, `/api/presets`, `/api/pattern`
  (Stage 1+2 → Qwen3-14B @ 8001, thinking, prompt_v8), `/api/visualise`
  (Stage 3 → Coder-32B @ 8004, google_charts).
- `index.html`: pick table + columns (or a blind-case preset) → Run Step 1+2 (shows pattern,
  recommended chart, mapping, full JSON) → Run Step 3 (renders the HTML inline in a sandboxed
  iframe, with a download link).
- `README.md`: tunnels required, startup, port-forwarding for remote browsing, configuration.
- Both model-backed endpoints verified end-to-end: `/api/pattern` 72s → `many_many_relationship`
  + Sankey + mapping; `/api/visualise` 281s → complete Google Sankey HTML (byte-identical to the
  CLI run).

## Work — 2026-06-15

Built and exercised an automated, end-to-end pipeline for pattern identification and chart mapping, and established the best-performing configuration.

Infrastructure:

- Added `experiments/scripts/run_pipeline.py`: a pure-standard-library pipeline that drives the self-hosted Qwen model through Stage 1+2 (pattern + mapping) and optional Stage 3 (HTML), writing a run directory (`metadata.json`, `responses/`, `raw/`) compatible with `evaluate_llm_run.py`.
- Confirmed cx3 firewalls cross-node ports, so the model must be reached over an SSH tunnel on `login-b` (`localhost:8001`), not by direct internal connection.
- Added a deterministic hybrid mode: `classify_vizer_pattern.py` assigns the pattern label and the LLM only does evidence + chart mapping.

Prompt iteration (pattern + mapping, Stage 3 skipped with `--skip-impl`):

- `prompt_v5_mcbrien`: zero-shot, McBrien & Poulovassilis conceptual-modelling grounding — pattern 5/9.
- `prompt_v6_hybrid`: deterministic label + LLM mapping — pattern 9/9, visualisation-overlap 9/9, but schema-evidence only 3/9 (the label is not LLM-derived).
- `prompt.md` / `prompt_v8.md`: full-LLM prompts folding in the `pattern_notes.md` rules and chart groups, then hardened iteratively.

Prompt hardening (full-LLM path):

- Split the many-many vs reflexive-many-many decision into two explicit trace steps, gated on a derived `two_primary_key_foreign_keys_reference_same_parent` field (fixes `borders`).
- Gated the weak vs one-many boundary on the structured `foreign_keys_in_primary_key` / `foreign_keys_not_in_primary_key` fields, and reordered the output so `identified_pattern` is emitted after the evidence (fixes the "evidence right, label wrong" inversions).
- Added a strict selected-columns-only scope so the model cannot introduce foreign keys the user did not select (fixes `organization`).

Key finding — Qwen thinking mode:

- The recurring errors were reasoning-consistency failures (correct structured evidence, contradictory final label), not knowledge gaps.
- Enabling thinking mode resolves them. **Best configuration: `prompt_v8.md` + `--enable-thinking` + `--pattern-max-tokens 12288`**, giving pattern **9/9**, visualisation-overlap **9/9**, schema-evidence **8/9**, exact-visualisation-set **2/9** (`experiments/results/prompt_v8_thinking`). This matches the hybrid on pattern/visualisation but is fully LLM-driven and far stronger on schema-evidence.
- Operational note: thinking traces are long; the default 8192 token cap truncates the longest case (`economy`) before any JSON is emitted, so `--pattern-max-tokens 12288` is required. Cost is roughly 90–156s per case (~15 min for all nine) versus ~54s without thinking.

Evaluation fix:

- `evaluate_llm_run.py::normalise_label` now reads `chart_type` from object-shaped `recommended_visualisations` entries (thinking mode emits objects), and the prompts require a flat string list. Without this the visualisation-overlap metric collapsed to a false 3/9.

Relevant output locations:

- `experiments/results/prompt_v5_mcbrien`, `prompt_v6_hybrid`, `prompt_v7_notes`, `prompt_v7_notes_thinking`, `prompt_v8_thinking`

## Work — 2026-06-09

The work focused on improving the third stage of the experiment: generating higher-quality visualisations after schema-pattern classification and chart mapping.

Work completed:

- Updated the modified Sankey diagram prompt in `experiments/results/prompt_v4`.
- Tested the revised Sankey prompt on the many-many `encompasses` case.
- Addressed the visual issue where the Kazakhstan-to-Europe link overlapped with many other links in the country-continent Sankey diagram.
- Generalised the Sankey prompt so that it is not only specific to the Mondial dataset, but can be applied to Sankey diagrams for other many-many relationship datasets.
- Added an area-weighted Sankey prompt that considers the `country.area` attribute.
- In the area-weighted design, country-side node sizes and link widths can be based on `area * percentage / 100`, while continent-side node sizes represent total incoming area contribution.
- Added a prompt for reflexive many-many relationships using chord diagrams.
- Tested chord diagram generation for reflexive relationship cases and saved the corresponding visualisation results in `experiments/results/prompt_v4`.

Relevant output location:

- `experiments/results/prompt_v4`

## Current Position

Stage 1+2 (pattern identification and chart mapping) is now automated and performing well: the full-LLM `prompt_v8` + thinking-mode configuration reaches 9/9 pattern accuracy and 9/9 visualisation-overlap on the nine blind cases, without the deterministic hybrid assist.

The main focus is now the visualisation implementation phase (Stage 3). A controlled two-model
comparison on case8 has established a working Stage 3 setup — **Coder-32B (thinking off) +
google_charts** — and shown that the 16k context window, not model skill, is the dominant
constraint, and that thinking mode (which helps Stage 1+2) hurts Stage 3. All three stages are
now driveable interactively through the web front-end (`experiments/web/`). The open Stage 3
questions remain whether the LLM can implement the selected visualisation in a way that is:

- faithful to the schema-pattern mapping
- visually readable
- aesthetically acceptable
- generalisable beyond one specific Mondial case

A controlled 16k-vs-32k test (Qwen3-14B, second instance at `--max-model-len 32768`) sharpened this:
Stage-3 failures split into two independent axes — a *context-budget* axis (truncation, `<think>`
leak, data-stubbing) that **scales away with a larger window** (32k turns the truncated d3 run into
a complete 251-row file), and a *library-version / graph-construction* axis (deprecated APIs, wrong
CDN pairing, malformed node/link building) that **does not respond to context** and is fixed only by
prompt constraints. So even with enough context the model can still get the chart's
graph-construction logic and library version wrong; closing that with stronger, pattern-specific
prompts is part of the next step.

## Next Planned Work

The next plan is to create more specialised implementation prompts for other ER schema patterns and their corresponding visualisations.

Examples include:

- `basic_entity` with bar charts, scatter charts, bubble charts, calendar charts, choropleth maps, or word clouds
- `weak_entity` with line charts, grouped bar charts, stacked bar charts, or spider/radar charts
- `one_many_relationship` with treemaps, hierarchy trees, or circle packing
- `many_many_relationship` with Sankey diagrams
- `reflexive_many_many_relationship` with chord diagrams or network-style visualisations

The aim is to build a prompt set where each schema pattern and chart type has clearer implementation guidance, rather than relying on one generic visualisation implementation prompt for all chart families.

### Relationship-visualisation design proposals (under review)

A separate strand explores expanding the chart set for the `many_many_relationship` and
`reflexive_many_many_relationship` patterns (matrix heatmap, force-directed graph, arc diagram,
hierarchical edge bundling, parallel sets). A Mondial audit found that `is_member` and `merges_with`
cannot be visualised today because Sankey/chord both require a scalar width; a matrix/force/arc keyed
on count or category closes that gap. Two written alternatives are awaiting a decision:

- `experiments/relationship_viz_proposal_v1_extend_taxonomy.md` — add new schema patterns (Step 1
  changes), each licensing a chart group.
- `experiments/relationship_viz_proposal_v2_charts_and_selector.md` — keep the six patterns; add the
  charts plus a deterministic Step-2 selector (density / N / symmetry / attribute types).

Note from the audit: Mondial has **no temporal** relationship attribute and **no directed** reflexive
relation, so the temporal and directed-reflexive ideas are scoped as future work, not built.
