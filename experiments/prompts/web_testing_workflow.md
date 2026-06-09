# Web Chat Testing Workflow

Use this workflow when testing through a web chatbox without an API.

## Step 1+2: Pattern And Chart Mapping

In a fresh chat, provide:

1. `experiments/prompts/mondial_pattern_prompt.md` as the system/task prompt.
2. `experiments/pattern_notes.md` as background knowledge.
3. `experiments/generated/mondial_schema_summary_clean.json` as schema background.
4. One blind case from `experiments/inputs/mondial_blind_cases.json`.

Ask the model to return JSON only. Save the response under a run directory, for example:

```text
experiments/results/prompt_v3_mp18a_mapping/responses/case_8.json
```

Evaluate the run with:

```bash
python experiments/scripts/evaluate_llm_run.py --run-dir experiments/results/prompt_v3_mp18a_mapping --gold experiments/inputs/mondial_gold_patterns.json --schema experiments/generated/mondial_schema_summary_clean.json
```

## Step 3: Library-Specific Visualisation

For each target library, start a separate fresh chat so previous library outputs do not influence the next result.

Use:

1. `experiments/prompts/visualisation_implementation_prompt.md`.
2. The step 1+2 JSON response for the case.
3. The relevant data JSON, e.g. `experiments/generated/mondial_encompasses_data.json` for case 8.
4. One target library name: `D3.js`, `Google Charts`, `Vega-Lite`, or another library.

Save each generated HTML file separately:

```text
experiments/results/visualisation_case_8/d3/response.html
experiments/results/visualisation_case_8/google_charts/response.html
experiments/results/visualisation_case_8/vega_lite/response.html
```

Record manual observations in a `notes.json` file for each library:

```json
{
  "case_id": "8",
  "library": "Google Charts",
  "runnable": true,
  "library_correct": true,
  "chart_type_correct": true,
  "mapping_correct": true,
  "data_used_correctly": true,
  "issues": []
}
```

For case 8, a faithful Sankey implementation should use:

- source = `country`
- target = `continent`
- weight = `percentage`

For Sankey-specific implementation tests, use these prompt variants:

```text
experiments/results/prompt_v3/visualisations/prompts/sankey_overlap_reduction_prompt.md
experiments/results/prompt_v3/visualisations/prompts/sankey_area_weighted_prompt.md
```

The overlap-reduction prompt keeps the original weight semantics and focuses on ordering, spacing, opacity, and routing. The area-weighted prompt changes the link weight to a derived area contribution and requires:

```text
experiments/generated/mondial_country_area.json
```

For a smaller South America-only test, use:

```text
experiments/prompts/visualisation_implementation_prompt_south_america.md
experiments/generated/mondial_encompasses_south_america_data.json
```

The South America-specific prompt already sets the data filter:

```text
continent == "South America"
```
