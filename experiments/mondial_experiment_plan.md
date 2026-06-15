# Mondial Schema Pattern Experiment Plan

## Goal

Test whether an LLM can recognise Mondial DATA-FIRST column selections as ER visualisation schema patterns and generate suitable visualisation mappings.

The redesigned experiment follows Mohammed Hannan's 2024 VizER report. The user selects a table and columns; the system first identifies the ER schema pattern from primary-key and foreign-key structure, then recommends chart types from the pattern's visualisation group.

The experiment starts with the Mondial relational schema because it is used in the McBrien and Poulovassilis papers and in the VizER report. It contains examples of:

- basic entities: `country`, `lake`, `organization`
- weak entities: `country_population`
- one-many relationships: `country` to `province`
- many-many relationships: `country` to `continent` through `encompasses`
- reflexive many-many relationships: `country` to `country` through `borders`
- basic entity with inherited key: `economy`, `population`

## Experiment Questions

1. Can the model identify selected columns, primary keys, attributes, and foreign keys from a selected table?
2. Can the model infer cardinality constraints from primary keys and foreign keys?
3. Can the model match a DATA-FIRST column selection to the correct VizER ER schema pattern?
4. Can the model recommend visualisations that fit the pattern?
5. Can the model produce a chart-ready mapping for Google Charts or Vega-Lite?
6. Can the model identify when a transformation is required?

## Initial Test Cases

The current cases are defined in `inputs/mondial_gold_patterns.json`:

| Case | Expected pattern | Example visualisation |
| --- | --- | --- |
| `hannan_basic_country_bar` | basic entity | bar chart |
| `hannan_basic_inherited_economy_scatter` | basic entity with inherited key | scatter chart |
| `hannan_basic_lake_bubble` | basic entity | bubble chart |
| `hannan_basic_organization_calendar` | basic entity | calendar chart |
| `hannan_weak_country_population_line` | weak entity | line chart |
| `hannan_weak_ethnic_group_grouped_bar` | weak entity | grouped bar chart |
| `hannan_one_many_airport_island_treemap` | one-many relationship | treemap |
| `hannan_many_many_encompasses_sankey` | many-many relationship | sankey diagram |
| `hannan_reflexive_many_many_borders_chord` | reflexive many-many relationship | chord diagram |

## Method

1. Extract a compact JSON summary from `mondial_schema.sql`.
2. Generate one LLM task per gold-standard selected-column case.
3. Run the deterministic VizER-style rule baseline to verify the gold cases.
4. Send the task to candidate LLMs.
5. Store raw model outputs in `outputs/`.
6. Score each output using:
   - exact checks for pattern names and transformations;
   - rubric-based qualitative judgement for schema reasoning and mapping quality.

## Candidate Models

Start with prompt-only experiments:

- GPT-family model available through the OpenAI API
- a strong open model if available locally or through an API
- a smaller/cheaper model to test whether this task needs advanced reasoning

Only consider fine-tuning after prompt-only results show repeated, systematic failures that cannot be fixed by schema representation or prompt design.

## Evaluation

Use `rubrics/mondial_pattern_matching_rubric.md`.

For each case, score:

- schema elements
- cardinality reasoning
- pattern classification
- transformation reasoning
- visualisation choice
- chart mapping

Maximum score: 12 per case.

## Commands

From repository root:

```bash
python experiments/scripts/extract_mondial_schema.py --schema experiments/mondial_database/mondial_schema.sql --out experiments/generated/mondial_schema_summary.json
python experiments/scripts/generate_clean_schema_summary.py --schema experiments/generated/mondial_schema_summary.json --out experiments/generated/mondial_schema_summary_clean.json
python experiments/scripts/generate_tasks.py --schema experiments/generated/mondial_schema_summary.json --patterns experiments/inputs/mondial_gold_patterns.json --out experiments/generated/mondial_llm_tasks.json
python experiments/scripts/classify_vizer_pattern.py --schema experiments/generated/mondial_schema_summary.json --cases experiments/inputs/mondial_blind_cases.json --out experiments/generated/vizer_rule_predictions.json
python experiments/scripts/evaluate_vizer_baseline.py --predictions experiments/generated/vizer_rule_predictions.json --gold experiments/inputs/mondial_gold_patterns.json --out experiments/generated/vizer_rule_baseline.json
```

## Next Step

The next implementation step is to add a runner that calls one or more LLM APIs, saves responses, and produces a comparison table in `results/`.
