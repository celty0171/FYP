# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A final-year research project (not a shipped product) investigating whether LLMs can match
**VizER / McBrien–Poulovassilis "visualisation schema patterns"** against a database schema and
then generate effective web-based visualisations. The work is experiment-driven: Python scripts
prepare schema/task inputs and score model outputs, while the LLM itself is exercised either through
self-hosted Qwen models on the Imperial HPC or, where no API is available, manually through web chat.

`project description.md` is the official brief; `PROJECT_STATUS.md` tracks current stage and next
steps; `experiments/README.md` and `experiments/mondial_experiment_plan.md` describe the active
experiment in detail. Read these before making research decisions.

## The experiment pipeline (Mondial dataset)

Everything centres on `experiments/`. The conceptual flow, with the script for each stage, run from
the repo root:

1. **Extract schema** — `scripts/extract_mondial_schema.py` parses `mondial_schema.sql` into a JSON
   summary (tables, columns, primary keys, foreign keys).
2. **Clean summary** — `scripts/generate_clean_schema_summary.py` produces the *clean* schema
   (`mondial_schema_summary_clean.json`): PK/FK/type evidence **without** derived pattern labels.
   This is the version fed to LLMs so they cannot see the answer.
3. **Generate tasks** — `scripts/generate_tasks.py` builds one DATA-FIRST task per case (a user
   selection of one table + several columns) from the schema and gold patterns.
4. **Deterministic baseline** — `scripts/classify_vizer_pattern.py` predicts the pattern from PK/FK
   structure alone, then `scripts/evaluate_vizer_baseline.py` scores it against gold. This rule
   baseline is what the LLM is compared against.
5. **Run the LLM** — submit each task to a model; save raw JSON responses (see run layout below).
6. **Evaluate the LLM run** — `scripts/evaluate_llm_run.py` scores a whole run directory.

Convert Mondial INSERT data to JSON with `scripts/convert_mondial_data_to_json.py` (optionally
`--table <name>` for a single table) for the visualisation-generation step.

### Critical invariant: blind vs gold separation

The baseline is **deliberately split** so prediction never sees the answer. `mondial_blind_cases.json`
(case id + selected table + columns only) drives `classify_vizer_pattern.py`; the gold file
(`mondial_gold_patterns.json`, with expected patterns/visualisations) is read **only** by the
evaluation step, after predictions are written. Preserve this separation — do not let pattern labels,
expected visualisations, or reasoning leak into anything an LLM or the classifier reads.

### The pattern taxonomy

The ER patterns are the core domain vocabulary: `basic_entity`, `basic_entity_inherited_key`,
`weak_entity`, `one_many_relationship`, `many_many_relationship`,
`reflexive_many_many_relationship`. The exact classification rules (and the boundary between
inherited-key basic entity and weak entity) are encoded in `classify_vizer_pattern.py::classify_selection`
— treat that function as the source of truth when reasoning about pattern definitions.

### Run directory & evaluation contract

`evaluate_llm_run.py` expects a run dir containing `metadata.json` and `responses/*.json`. Each
response JSON carries `case_id`, `identified_pattern`, `recommended_visualisations`, and a
`schema_evidence` object; the evaluator normalises visualisation aliases (see `VISUALISATION_ALIASES`)
and writes `evaluation.json`, `summary.json`, and `summary.md`. Match this shape when adding new runs
or changing prompts that produce these fields. See `results/prompt_v2_clean_schema/` for a complete
worked example (incl. `metadata.json` fields).

## The LLM-as-compiler pipeline (deterministic Step 1→2→3)

As of 2026-06-23 the project added a second paradigm alongside per-case prompting: instead of asking
an LLM to answer each case at run time, prompts ask the LLM to **author a deterministic Python
program once** ("compile time"), which then runs reproducibly with data read at run time (never in the
prompt). This dissolves the two documented Stage-3 failure axes (context-budget + library-version
drift). All three steps now exist as LLM-authored standard-library programs with aligned contracts.

- **Step 1 — pattern classifier.** Prompt `prompts/prompt_v9.md` (v8's Step-1 half, retasked to emit
  code) → `results/prompt_v9_codegen/`: `classifier_generated.py` (reference) and `gpt_generated.py`
  (GPT-authored, stricter on partial-PK selections), both 9/9 on the blind cases.
- **Step 2 — chart recommendation + mapping.** Prompt `prompts/step2_chart_mapping_prompt.md` (latest
  `_v4.md`) → `results/step2_codegen/`: `recommend_charts_reference.py` and `gpt_recommend_charts.py`.
  Emits recommended charts + a mapping whose field names match exactly what the Step-3 renderers read.
  For the two many-many patterns it runs a **data-driven relationship selector** (proposal v2 §4):
  it measures `density`, `N` and `symmetric` from the rows and ranks charts by an ordered rule table —
  node-link (Sankey/chord) only while a relationship is sparse & small & has a scalar; once **dense or
  large** the **matrix heatmap** leads; matrix/force also carry `value` = a scalar column **or** the
  literal `"count"`, so attribute-free relations (`is_member`, `merges_with`) are covered. Thresholds
  `DENSE`/`LARGE_N`/`SYMMETRIC_MIN`. `gpt_recommend_charts.py` is the authoritative data-driven one
  (server loads it); the reference is a schema-only sibling.
- **Step 3 — renderers.** Layered prompts in `prompts/viz_codegen/`: shared `base_d3v7.md` (D3 v7
  contract, interactivity, no brace-templating rule) + one `chart_<x>.md` per chart, concatenated at
  runtime. One renderer per chart lives in `results/viz_codegen_<chart>/render_<chart>_reference.py`,
  each `render(mapping, rows)` reading grouped `mondial_database/mondial_data.json` via
  `mapping["table"]`. All 5 patterns / 18 charts built (every chart Step 2 can recommend): bar,
  scatter, bubble, calendar, choropleth, word cloud (basic); line, stacked, grouped, spider (weak);
  treemap, circle packing, hierarchy tree (one_many); and for **both** many_many and reflexive_many_many:
  sankey + chord (node-link, pattern-aware: sankey namespaces the two sides, chord is bipartite for
  many_many / shared-set for reflexive), **matrix heatmap** (`viz_codegen_matrix`, square-symmetric vs
  bipartite, count fallback), **force graph** (`viz_codegen_force`, topology), and **arc diagram**
  (`viz_codegen_arc`, **reflexive-only**). matrix/force/arc read `mapping["value"]` (scalar column or
  `"count"`), matrix also an optional `category`. Each run dir has a `SUMMARY.md`.
- **Web front-end.** `experiments/web_pipeline/` (`server.py` + `index.html`, std-lib
  ThreadingHTTPServer, **no model calls at serve time**) chains the three programs and renders the
  result in a sandboxed iframe; unbuilt charts return `"working in process"`.

## Production layer (opt-in — live SQL + natural-language input)

An optional deployment layer sits **in front of** the pipeline without changing any of the above;
it is off by default so the experiment path is byte-identical. Configured via a repo-root `.env`
(gitignored; template `.env.example`), read by `experiments/config.py`. Needs
`experiments/requirements.txt` (SQLAlchemy + psycopg2 + openai) — the experiment core stays std-lib.

- **Data-source adapter** `experiments/datasource/` — a `DataSource` yields the *same* clean schema
  dict + row dicts the pipeline consumes, from either the offline JSON files (`JsonFileDataSource`,
  default `VIZER_DATASOURCE=json`) or a live PostgreSQL DB (`PostgresDataSource`, SQLAlchemy `inspect`
  for PK/FK/types, `SELECT … LIMIT` for rows with type coercion). `make_datasource(load_config())`
  picks one; `server.py` reads `SCHEMA`/`TABLES` from it instead of the two JSON globals.
- **NL → selection** `experiments/nlquery/` — `nl_to_selection.parse(text, schema)` uses the Bailian /
  DashScope OpenAI-compatible client (`bailian_client.py`, key `DASHSCOPE_API_KEY`) to turn free text
  into a validated `{table, columns, filters, joins, aggregate}` selection — **never** a pattern or
  chart label, so blind/gold separation holds. For a non-aggregate data-first selection it
  deterministically ensures the base table's **primary-key column(s)** are in `columns`
  (`_ensure_identifying_columns`), so Step 2 always has a key/region/text role and real candidates.
  Served at `POST /api/nl` (returns the selection for the UI to confirm, then run via `/api/run`);
  degrades gracefully when no key is set.
- **LLM chart selection (Step 2)** `experiments/chartselect/` — opt-in (`VIZER_LLM_STEP2=on`,
  default `off`). `llm_chart_selector.select(schema, table, columns, pattern, s2, client, rows, intent)`
  asks the Bailian client to **rank every deterministic Step-2 candidate** (each with a one-line note),
  pick one to highlight, give one short English rationale, and optionally swap a selected column into an
  **existing** mapping role (same dimension only) — it never invents charts, mapping keys, or column
  names, and never sees a gold label, so both the blind/gold separation and the Step-2→Step-3
  field-name contract hold. It is **intent-aware** (the user's request flows through as a soft *goal*
  signal) and **data-aware** (deterministic row-count / cardinality / null-share / numeric-range
  signals), so the same columns under different goals or data scales can lead to different charts.
  Wired in `server.py::_step2_block` (both the aggregate and non-aggregate paths, fed `rows`+`intent`
  from `run_pipeline`; `/api/run` reads `intent`, the UI's optional purpose box prefilled from the NL
  request): all valid candidates are still returned, `step2.llm = {recommended_chart, reason, source,
  ranking:[{chart,note}]}` is added, and the highlighted chart becomes `selected` for Step 3. Any
  error/invalid answer → deterministic pick (`source="fallback"`). Conditional candidates
  (choropleth/word cloud, which need a geographic/lexical key unprovable from schema) are in the
  selector's pool but flagged `[CONDITIONAL]` — the LLM may elevate one only when the goal/columns
  justify it, while the deterministic pick and fallback stay True-eligible only. Prompt contract
  documented in `prompts/step2_llm_select_prompt.md`.

The Step-2→Step-3 mapping field-name contract and the base-renderer rules (thinking off,
`repetition_penalty=1.1`, no f-string/`.format()` brace templating, structural + static-JS validation)
are the source of truth for extending these — see `prompts/viz_codegen/base_d3v7.md` and each cell's
`SUMMARY.md`.

## Commands

Scripts use **only the Python standard library** — no install step, no test suite, no linter.
Invoke directly with `python experiments/scripts/<name>.py --help` to see arguments. The canonical
multi-step invocations are listed in `experiments/README.md` and `experiments/mondial_experiment_plan.md`;
prefer copying from there since paths and flags are exact. They read the in-repo SQL under
`experiments/mondial_database/` and write outputs under `experiments/generated/`.

## LLM access

Two modes; `PROJECT_STATUS.md` reflects the current one.

- **Self-hosted Qwen on HPC** — `最最新_HPC_Qwen_速查表.md` is the full operations manual (Imperial
  cx3 cluster, vLLM serving 8 Qwen models on ports 8001–8008, reached over an SSH tunnel). Models
  expose an **OpenAI-compatible API**; `qwen3_test.py` is the minimal client example
  (`base_url="http://localhost:<port>/v1"`, dummy key, `model="<served-name>"`). Qwen2.5-Coder-32B
  (port 8004) is noted as best for visualisation/code generation.
- **Manual web chat** — when no API is available, follow `experiments/prompts/web_testing_workflow.md`:
  Steps 1+2 use `prompts/mondial_pattern_prompt.md` + `pattern_notes.md` + the clean schema to get the
  pattern and chart mapping; Step 3 uses `prompts/visualisation_implementation_prompt.md` + the
  relevant data JSON to generate runnable standalone HTML (D3 / Google Charts).

## Conventions

- Prose, prompts, and reports are written in **British English** (e.g. "visualisation"); the HPC cheat
  sheet and some notes are in Chinese. Match the language and spelling of the file you are editing.
- Generated artefacts go in `experiments/generated/`; raw model outputs in `experiments/outputs/` or a
  versioned `experiments/results/<run>/`. `.venv/` and `__pycache__/` are gitignored.
- Prompt iterations are versioned by directory (`results/prompt_v2…`, `prompt_v3`, `prompt_v4`); add a
  new `prompt_vN` rather than overwriting prior results.
