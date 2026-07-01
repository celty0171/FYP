# Mondial Pattern Prompt — Hybrid (deterministic pattern + LLM visualisation mapping)

You are evaluating a DATA-FIRST column selection from the Mondial relational database, using the
conceptual-modelling approach of McBrien and Poulovassilis ("Towards Data Visualisation based on
Conceptual Modelling and Schema Transformations", AutoMed Technical Report 39).

The ER visualisation schema pattern for this selection has **already been determined
deterministically** from the primary-key / foreign-key structure of the schema:

```text
{{GIVEN_PATTERN}}
```

Treat this pattern as correct and fixed. Do **not** re-classify it. Your job is to:

1. record the schema evidence (PK/FK structure) that is consistent with this pattern;
2. explain the relationship cardinalities implied by that structure;
3. recommend the visualisations that are valid for this pattern and that can actually be mapped
   to the selected columns;
4. produce an explicit chart-ready mapping.

## Dimension types (these decide chart eligibility)

Classify each selected attribute as one of two dimension types:

- **scalar dimension**: a large number of distinct values with a natural numeric ordering —
  integers, floats/decimals, and temporal values (dates, years, timestamps). Represented by a
  channel (length, position, size, colour spectrum). Infer scalar from SQL numeric/temporal types.
- **discrete dimension**: a relatively small number of distinct values, possibly unordered — used
  to choose a mark or vary a channel via a colour key. Infer discrete from short text/code types.

A dimension may also carry a real-world character enabling specific charts: **geographical**
(region key → choropleth), **temporal** (date/year → calendar / time axis), **lexical**
(words/labels key → word cloud). Only assert these when the column type and role support it.

## Visualisation eligibility for the given pattern

Recommend only the charts whose mandatory variables can be mapped to selected columns of the
right dimension type. Do not list every chart in a group. Cardinality bounds (|k| = number of
distinct key values) are aesthetic guidance, not hard limits.

`basic_entity` and `basic_entity_inherited_key` (entity `E`, key `k`, attributes `a1, a2, …`;
for an inherited key, `k` is the inherited parent key):
- bar chart — key `k`, one scalar `a1` (|k| up to ~100).
- calendar chart — a temporal `a1` (optional scalar `a2` colour).
- scatter chart — two scalar attributes `a1`, `a2` (optional `a3` colour).
- bubble chart — three scalar attributes `a1`, `a2`, `a3` (optional `a4` colour).
- choropleth map — `k` geographical, scalar/colourable `a1`.
- word cloud — `k` lexical, scalar `a1` (optional `a2` colour).

`weak_entity` (`k1` parent key, `k2` local key, `a1` scalar measure):
- line chart — scalar `k2` on x-axis, scalar `a1` on y-axis (optional `a2`); no completeness needed.
- stacked bar chart — scalar `a1`; best when `k2` values are complete across `k1`.
- grouped bar chart — scalar `a1`; no completeness needed.
- spider chart — scalar `a1`; best with complete `k2` across `k1` (|k1| ~3..10).

`one_many_relationship` (`Ep` parent, `Ec` child, `kp`/`kc` keys, `a1` scalar child measure):
- treemap — requires scalar `a1` (optional `a2` colour).
- hierarchy tree — needs only parent/child keys (optional discrete `a1` to colour links).
- circle packing — requires scalar `a1` (optional `a2` colour).

`many_many_relationship` (`E1`, `E2` parents, `k1`/`k2` foreign keys, `a1` scalar relationship
attribute):
- sankey diagram — non-reflexive links; source = `k1`, target = `k2`, width = scalar `a1`
  (optional `a2` colour).

`reflexive_many_many_relationship` (single parent `E`, `k1`/`k2` foreign keys, `a1` scalar
relationship attribute):
- chord diagram — points around a circle are instances of the single entity `E`; scalar `a1`
  sets connection width (optional `a2` colour).

## Transformations

If the raw selection does not directly fit the chosen chart, note the schema transformation
required (e.g. **pivot** instances into columns; **denormalise / roll-up / drill-down**) in
`required_transformations`; leave empty when none is needed.

## Output

Return JSON only, with exactly this shape. Set `identified_pattern` to the given pattern above.

```json
{
  "case_id": "...",
  "identified_pattern": "{{GIVEN_PATTERN}}",
  "confidence": 0.0,
  "schema_evidence": {
    "selected_table": "",
    "selected_columns": [],
    "primary_key_columns": [],
    "foreign_key_columns": [],
    "selected_foreign_key_columns": [],
    "foreign_keys_in_primary_key": [],
    "foreign_keys_not_in_primary_key": [],
    "local_primary_key_columns": [],
    "primary_key_is_compound": false,
    "all_primary_key_columns_are_foreign_keys": false,
    "rule_decision_trace": [
      { "rule": "many_many_or_reflexive", "matched": false, "reason": "" },
      { "rule": "basic_entity_inherited_key", "matched": false, "reason": "" },
      { "rule": "weak_entity", "matched": false, "reason": "" },
      { "rule": "one_many_relationship", "matched": false, "reason": "" },
      { "rule": "basic_entity", "matched": false, "reason": "" }
    ],
    "cardinality_reasoning": ""
  },
  "recommended_visualisations": [],
  "visualisation_candidates": [
    {
      "chart_type": "",
      "eligible": true,
      "eligibility_reason": "",
      "schema_pattern_variables": {},
      "encoding": {},
      "required_transformations": [],
      "limitations": []
    }
  ],
  "selected_visualisation": {
    "chart_type": "",
    "selection_reason": "",
    "schema_pattern_variables": {},
    "encoding": {},
    "required_transformations": [],
    "library_notes": { "d3": "", "google_charts": "", "vega_lite": "" }
  },
  "chart_mapping": {},
  "data_type_reasoning": "",
  "limitations": []
}
```

Use `data_type_reasoning` to record which selected columns you treated as scalar vs discrete (and
any geographical/temporal/lexical character) and why.

Selection:

```json
{{SELECTION}}
```

Schema fragment:

```json
{{SCHEMA_FRAGMENT}}
```
