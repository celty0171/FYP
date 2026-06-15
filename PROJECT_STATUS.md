# Project Status

## Current Stage

Date: 2026-06-15

The project is currently at the stage of testing whether LLMs can accurately identify visualisation schema patterns and then implement visually effective web-based visualisations.

LLM access is now automated. A self-hosted Qwen3-14B model runs on the Imperial HPC (cx3) under vLLM with an OpenAI-compatible API, reached over an SSH tunnel on `localhost:8001`. An end-to-end pipeline (`experiments/scripts/run_pipeline.py`) drives the model through all three stages without manual web chat; manual web chat (GPT / Claude on the university agent platform) remains a fallback when the HPC model is unavailable.

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

The project therefore returns its main focus to the visualisation implementation phase (Stage 3). The current focus is whether the LLM can implement the selected visualisation in a way that is:

- faithful to the schema-pattern mapping
- visually readable
- aesthetically acceptable
- generalisable beyond one specific Mondial case

## Next Planned Work

The next plan is to create more specialised implementation prompts for other ER schema patterns and their corresponding visualisations.

Examples include:

- `basic_entity` with bar charts, scatter charts, bubble charts, calendar charts, choropleth maps, or word clouds
- `weak_entity` with line charts, grouped bar charts, stacked bar charts, or spider/radar charts
- `one_many_relationship` with treemaps, hierarchy trees, or circle packing
- `many_many_relationship` with Sankey diagrams
- `reflexive_many_many_relationship` with chord diagrams or network-style visualisations

The aim is to build a prompt set where each schema pattern and chart type has clearer implementation guidance, rather than relying on one generic visualisation implementation prompt for all chart families.
