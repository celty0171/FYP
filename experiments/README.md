# Mondial Schema Pattern Experiments

This experiment suite tests whether an LLM can identify visualisation schema patterns in the Mondial database and produce chart-ready visualisation mappings.

The current design follows Mohammed Hannan's 2024 VizER report: the unit of analysis is a DATA-FIRST user selection of columns from a single table.

The theoretical baseline comes from McBrien and Poulovassilis's visualisation schema patterns:

- basic entity
- basic entity with inherited key
- weak entity
- one-many relationship / hierarchy
- many-many relationship / network
- reflexive many-many relationship

The important boundary is that an inherited-key basic entity has no local primary-key column, while a weak entity has a compound primary key made from both inherited parent-key columns and local child-key columns.

### Design proposals — relationship visualisations (many-many / reflexive)

Two written proposals explore adding new charts for the `many_many_relationship` and
`reflexive_many_many_relationship` patterns (matrix heatmap, force-directed graph, arc diagram,
hierarchical edge bundling, parallel sets), motivated by an audit showing `is_member` and
`merges_with` cannot be drawn today (Sankey/chord both require a scalar width). They differ in *where*
the logic lives:

- [`relationship_viz_proposal_v1_extend_taxonomy.md`](relationship_viz_proposal_v1_extend_taxonomy.md)
  — adds new schema patterns (`weighted_/unweighted_`, `attributed_relationship`,
  `grouped_relationship`), each licensing a chart group (Step 1 changes).
- [`relationship_viz_proposal_v2_charts_and_selector.md`](relationship_viz_proposal_v2_charts_and_selector.md)
  — keeps the six patterns; adds the charts plus a deterministic Step-2 selector keyed on
  density / N / symmetry / attribute types (Step 1 unchanged).

## Main Research Question

Can an LLM inspect a selected Mondial table/column set, identify which VizER ER schema pattern is present, and generate a suitable visualisation mapping?

## Experiment Layers

1. Schema understanding
   - Identify the selected table, selected columns, primary keys, foreign keys, scalar attributes, and inherited keys.
   - Infer cardinalities from primary keys and foreign keys.

2. Pattern matching
   - Match selected columns to the VizER/Hannan pattern rules.
   - Explain why each pattern applies.

3. Visualisation generation
   - Select a suitable chart type.
   - Generate chart-ready mappings for Google Charts or Vega-Lite.
   - State required data transformations.

## Suggested Workflow

Run from this repository root:

```bash
python experiments/scripts/extract_mondial_schema.py --schema experiments/mondial_database/mondial_schema.sql --out experiments/generated/mondial_schema_summary.json
python experiments/scripts/generate_clean_schema_summary.py --schema experiments/generated/mondial_schema_summary.json --out experiments/generated/mondial_schema_summary_clean.json
python experiments/scripts/generate_tasks.py --schema experiments/generated/mondial_schema_summary.json --patterns experiments/inputs/mondial_gold_patterns.json --out experiments/generated/mondial_llm_tasks.json
python experiments/scripts/classify_vizer_pattern.py --schema experiments/generated/mondial_schema_summary.json --cases experiments/inputs/mondial_blind_cases.json --out experiments/generated/vizer_rule_predictions.json
python experiments/scripts/evaluate_vizer_baseline.py --predictions experiments/generated/vizer_rule_predictions.json --gold experiments/inputs/mondial_gold_patterns.json --out experiments/generated/vizer_rule_baseline.json
```

Then submit each generated task to an LLM and save raw responses in `outputs/`.
For agent-platform tests, use `generated/mondial_schema_summary_clean.json` as background schema knowledge so the model sees PK/FK/type evidence without derived pattern labels.

For web-chat testing without an API, follow `prompts/web_testing_workflow.md`:

- Step 1+2 uses `prompts/mondial_pattern_prompt.md` with `pattern_notes.md` and the clean schema summary to identify the schema pattern and MP18a chart mapping.
- Step 3 uses `prompts/visualisation_implementation_prompt.md` with a selected target library and the relevant data JSON to generate runnable HTML.
- For case 8, use `generated/case_8_visualisation_test_package.json` or the smaller `generated/mondial_encompasses_data.json`.

To convert Mondial INSERT data to JSON:

```bash
python experiments/scripts/convert_mondial_data_to_json.py --data experiments/mondial_database/mondial_data.sql --schema experiments/generated/mondial_schema_summary_clean.json --out experiments/generated/mondial_data.json
python experiments/scripts/convert_mondial_data_to_json.py --data experiments/mondial_database/mondial_data.sql --schema experiments/generated/mondial_schema_summary_clean.json --table encompasses --out experiments/generated/mondial_encompasses_data.json
```

The deterministic baseline is deliberately split into two steps: classification reads only blind cases, while evaluation reads the gold file only after predictions have been written.
