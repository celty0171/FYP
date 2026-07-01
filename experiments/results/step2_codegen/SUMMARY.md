# step2_codegen — Step 2 as deterministic programming (chart recommendation + Step-3 mapping)

Step 2 of the pipeline, in the same "LLM writes the program" paradigm proven for Step 1
(`prompt_v9_codegen`) and the Step-3 renderers. Instead of recommending charts per case by hand, the
model writes a deterministic program that, given the schema + a selection + its Step-1 pattern,
classifies each attribute's dimension type, checks each chart in the pattern's group against its
mandatory requirements, and emits a mapping whose field names are **exactly** what the Step-3
renderers consume.

## Basis

Rules from `experiments/pattern_notes.md` and *Towards Data Visualisation based on Conceptual
Modelling and Schema Transformations* (McBrien & Poulovassilis): the per-pattern visualisation
groups, each chart's mandatory checks (e.g. bar needs key + 1 scalar; scatter 2; bubble 3; line needs
scalar child key + scalar measure), and the schema-pattern mapping variables.

## Files

- `prompts/step2_chart_mapping_prompt.md` — the Step-2 prompt: dimension typing from SQL types,
  per-pattern chart groups + mandatory checks, and the **fixed Step-3 mapping field names** per chart.
- `recommend_charts_reference.py` — reference program (`recommend(schema, table, columns, pattern)` +
  `--schema/--cases/--out`).
- `cases_with_pattern.json` — the nine blind cases annotated with their Step-1 pattern (from the rule
  baseline), i.e. the real input shape Step 2 receives downstream of Step 1.
- `recommendations.json` — output for all nine cases.

## Result (nine cases)

| case | pattern | recommended | selected mapping |
|------|---------|-------------|------------------|
| 1 country | basic_entity | bar | `{key: code, measure: population}` |
| 2 economy | basic_entity_inherited_key | bar, scatter | `{key: country, x: gdp, y: unemployment}` |
| 3 lake | basic_entity | bar, scatter, bubble | `{key: name, x: elevation, y: depth, size: dam_height}` |
| 4 organization | basic_entity | calendar | `{date: established, key: abbreviation}` |
| 5 country_population | weak_entity | line, stacked, grouped, spider | line `{series: country, x: year, y: population}` |
| 6 ethnic_group | weak_entity | stacked, grouped, spider | stacked `{group: country, segment: name, value: percentage}` |
| 7 airport | one_many | tree map, circle packing, hierarchy tree | `{parent: island, child: iata_code, measure: elevation}` |
| 8 encompasses | many_many | Sankey | `{source: country, target: continent, width: percentage}` |
| 9 borders | reflexive_many_many | chord | `{source: country1, target: country2, width: length}` |

Dimension typing is correct throughout (e.g. case 4 picks **calendar** because `established` is `DATE`
and no scalar attribute is selected; case 5 picks **line** because `year` is a scalar child key).

## End-to-end check — Step-2 mapping → Step-3 renderer, zero glue

Each `selected.mapping` was fed straight into the matching Step-3 reference renderer against
`mondial_data.json`: **7/7 produced a complete HTML** (cases 1, 2, 3, 4, 7, 8, 9). Cases 5–6 (weak)
are skipped only because the weak-row renderers (line/stacked/spider) are not built yet — the mappings
themselves are well-formed. This confirms the Step-2 ↔ Step-3 contract: the field names Step 2 emits
(`key/measure`, `x/y/size`, `date/key`, `parent/child/measure`, `source/target/width`) are exactly the
ones the renderers read.

## Reproduce

```bash
cd experiments
python3 results/step2_codegen/recommend_charts_reference.py \
  --schema mondial_database/mondial_schema_summary_clean.json \
  --cases results/step2_codegen/cases_with_pattern.json \
  --out results/step2_codegen/recommendations.json
```

## Qwen3-14B provenance run (port 8001, thinking off, repetition_penalty 1.1)

`run_qwen_step2.py` sent `step2_chart_mapping_prompt.md` to `Qwen3-14B` (132 s, runnable program) and
ran it on the nine annotated cases. Agreement with the reference: **selected mapping 4/9,
recommended-set 4/9**.

- **Correct (4):** case 1 bar, 3 bubble, 4 calendar, 7 tree map — the cases whose column types are
  clean tokens (`INT`/`INTEGER`/`DATE`/`VARCHAR`).
- **Empty (5), two confirmed root causes in the generated program** (`qwen_recommend_charts.py`):
  1. **`dim_type` uses exact string matching** (`sql_type in ['NUMERIC', …]`) and never strips the
     `(precision)` suffix, so `NUMERIC(10,2)`, `NUMERIC(5,2)`, `VARCHAR(4)` all fall through to
     `None`. This drops the scalar attribute (width/measure/value) for case 8 (encompasses
     `percentage`), case 9 (borders `length`), case 6 (ethnic_group `percentage`), and `unemployment`
     in case 2.
  2. **No `basic_entity_inherited_key` branch** — it only handles `pattern == 'basic_entity'`, so the
     inherited-key case 2 falls through to empty.
  3. case 5 (weak) additionally produced nothing — its FK/role detection for `country_population`'s
     inferred foreign key diverges from the reference.

The reference avoids both: it matches SQL types by **prefix** (`t.startswith(p)`, so `NUMERIC(10,2)`
is scalar) and folds `basic_entity_inherited_key` into the `basic_entity` group. Same shape of finding
as Step 1 (8/9, inherited-key wording) and the chord cell (brace templating): Qwen produces a correct
*skeleton* but misses implementation details (here, parsing parameterised SQL types and the
inherited-key alias). Evidence: `qwen_recommend_charts.py`, `recommendations_qwen.json`,
`raw_qwen_step2.txt`.

### Hardened-prompt re-run (`step2_chart_mapping_prompt_v2.md`) — non-monotonic

A copy of the prompt was hardened on the two confirmed causes only: §1 now says SQL types carry a
`(precision)` suffix and must be matched by the leading type name (prefix), and §2 says the program
must branch on **both** `basic_entity` and `basic_entity_inherited_key`. Re-running the same
Qwen3-14B (thinking off, repetition_penalty 1.1):

- Both targeted bugs **did clear**: `NUMERIC(p,s)` columns are now recognised (cases 6/8/9 no longer
  empty) and the inherited-key case 2 enters the basic group.
- But the program **regressed elsewhere**: it stopped gating on mandatory requirements (cases 1–3
  recommend *all six* basic charts) and emitted **malformed mappings** mixing every field-name scheme
  with empty strings (e.g. case 8 `{source:'', target:'', width:'', key:continent, measure:percentage}`).
  Net: **selected mapping 0/9, recommended-set 3/9** — worse than the original 4/9.

Lesson (contrast with Step 1's clean 8/9→9/9 hardening): Step 2's program is far larger (six pattern
branches × several mapping shapes), and for a weak model a targeted prompt edit perturbs the **whole**
generation non-monotonically — fixing two local bugs while dropping eligibility gating and mapping
hygiene. This strengthens the case that complex Step-2/3 program authoring needs a stronger
code model (Coder-32B) and/or the reference as the trusted artifact. Evidence:
`qwen_recommend_charts_v2.py`, `recommendations_qwen_v2.json`, `raw_qwen_step2_v2.txt`.

### GPT provenance run (web chat, original prompt) — strong-model contrast

`gpt_recommend_charts.py` (authored by GPT from the **original** `step2_chart_mapping_prompt.md`) was
run on the same nine cases. Agreement with the reference: **recommended-set 9/9, selected chart 9/9,
selected mapping 7/9**, and **7/7 of its selected mappings rendered a complete HTML when fed straight
into the Step-3 renderers** (cases 5–6 weak, no renderer yet).

- The only two mapping diffs (cases 2, 3) differ solely by an extra **optional `color`** field, which
  GPT set to the key column (`country` / `name`) — defensible but unhelpful (every point a distinct
  colour); the Step-3 scatter/bubble renderer accepts the optional `color`, so it still renders.
- GPT handled exactly what Qwen missed with no prompt help: it parses parameterised SQL types, folds
  `basic_entity_inherited_key` into the basic group, and keeps eligibility gating + clean mappings.

| author / prompt | recommended | selected chart | selected mapping | → Step 3 |
|-----------------|-------------|----------------|------------------|----------|
| reference | 9/9 | 9/9 | 9/9 | 7/7 |
| **GPT (original prompt)** | **9/9** | **9/9** | **7/9** (2 × extra optional `color`) | **7/7** |
| Qwen3-14B (original prompt) | 4/9 | — | 4/9 | — |
| Qwen3-14B (hardened v2) | 3/9 | — | 0/9 | — |

**Takeaway:** for a complex step like Step 2, a strong code model authors a near-correct,
Step-3-aligned program in one shot, while the weak self-hosted model stalls on implementation details
and responds non-monotonically to prompt edits. "LLM-as-compiler" scales to the harder steps **given a
strong enough model**. Evidence: `gpt_recommend_charts.py`, `recommendations_gpt.json`.

## Status / next

- Reference done and validated end-to-end into Step 3. Provenance: GPT 9/9 recommended (original
  prompt); Qwen 4/9 original, 0/9 hardened v2.
- The weak-row renderers (line / stacked bar / spider) are the remaining Step-3 cells; once built,
  cases 5–6 close the end-to-end loop for all nine.
