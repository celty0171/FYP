# Mondial VizER-Style ER Pattern Prompt

You are evaluating a DATA-FIRST column selection from the Mondial database.

Follow the ER schema-pattern rules described in Mohammed Hannan's 2024 VizER report.

Do not classify from natural-language table meaning alone. Classify from the selected table's primary-key and foreign-key structure.

- `basic_entity`: the selected columns come from an entity with a primary key and attributes, with no selected foreign-key dependency.
- `basic_entity_inherited_key`: the whole primary key is inherited as a foreign key from one parent entity, with no local primary-key column; We treat this as a basic entity, not a weak entity.
- `weak_entity`: the table has a compound primary key; a proper subset of the primary key is a foreign key to one parent entity and at least one remaining primary-key column is local to the child entity.
- `one_many_relationship`: the selected columns include one foreign key to a parent entity, but that foreign key is not part of the table primary key.
- `many_many_relationship`: the table primary key consists of two foreign keys referencing two different parent tables.
- `reflexive_many_many_relationship`: the table primary key consists of two foreign keys referencing the same parent table.

Use this decision order. Apply the first matching rule, and explain the decision using PK/FK evidence:

1. If the full table primary key has at least two columns and every primary-key column is a foreign key, classify as `many_many_relationship` when the foreign keys reference different parent tables, or `reflexive_many_many_relationship` when they reference the same parent table.
2. Else if the whole primary key is inherited as a foreign key from one parent entity and there is no local primary-key column, classify as `basic_entity_inherited_key`.
3. Else if the table primary key is compound and contains both foreign-key columns and local primary-key columns, classify as `weak_entity`.
4. Else if the selected columns include a foreign key that is not part of the table primary key, classify as `one_many_relationship`.
5. Else classify as `basic_entity`.

Important boundary checks:

- Do not classify a weak entity as `one_many_relationship` merely because it has a parent foreign key. If that foreign key is part of the table primary key and there is also a local primary-key column, the pattern is `weak_entity`.
- Do not classify a selection as `basic_entity` merely because the table has its own primary key and scalar attributes. If a selected foreign key is not part of the primary key, the pattern is `one_many_relationship`.

Then recommend visualisations using the chart eligibility rules and the selected columns' data types. Do not merely list every chart in the pattern group. For each recommended chart, verify that the mandatory variables required by the chart can be mapped to selected columns.

- Basic entity: bar chart, calendar chart, scatter chart, bubble chart, choropleth map, word cloud.
- Weak entity: line chart, stacked bar chart, grouped bar chart, spider chart.
- One-many relationship: treemap, hierarchy tree, circle packing.
- Many-many relationship: sankey diagram.
- Reflexive many-many relationship: chord diagram.

Use these mapping variables:

- Basic entity: map `E` to the selected table, `k` to the entity key, and `a1/a2/a3/a4` to selected attributes that satisfy chart type requirements.
- Weak entity: map `k1` to the parent-key foreign-key portion of the primary key, `k2` to the local child key, and `a1` to the scalar measure.
- One-many relationship: map `Ep` to the parent table referenced by the selected non-primary foreign key, `Ec` to the selected child table, `kp` to the selected FK, `kc` to the child key, and `a1` to a scalar child attribute when needed.
- Many-many relationship: map `E1` and `E2` to the two referenced parent tables, `R` to the relationship table, `k1/k2` to the two foreign keys, and `a1` to the scalar relationship attribute used as flow/link weight.
- Reflexive many-many relationship: map `E` to the single referenced parent entity, `R` to the relationship table, `k1/k2` to the two foreign keys, and `a1` to the scalar relationship attribute used as connection width.

Chart eligibility rules:

- Bar chart requires one scalar `a1`; calendar requires a temporal `a1`; scatter requires two scalar attributes; bubble requires three scalar attributes; choropleth requires a geographical key; word cloud requires a lexical key plus scalar `a1`.
- Weak-entity line chart requires scalar `k2` and scalar `a1`; stacked/grouped bar and spider require scalar `a1`; stacked bar and spider also prefer complete `k2` values across `k1`.
- Treemap and circle packing require parent key, child key, and scalar child measure `a1`; hierarchy tree requires parent key and child key, with optional colour.
- Sankey requires non-reflexive many-many links plus scalar relationship attribute `a1`; source must be `k1`, target must be `k2`, width/weight must be `a1`.
- Chord is especially suitable for reflexive many-many relationships; source and target are the two foreign keys and width is scalar `a1`.

Return JSON only with this shape:

```json
{
  "case_id": "...",
  "identified_pattern": "...",
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
      {
        "rule": "many_many_or_reflexive",
        "matched": false,
        "reason": ""
      },
      {
        "rule": "basic_entity_inherited_key",
        "matched": false,
        "reason": ""
      },
      {
        "rule": "weak_entity",
        "matched": false,
        "reason": ""
      },
      {
        "rule": "one_many_relationship",
        "matched": false,
        "reason": ""
      },
      {
        "rule": "basic_entity",
        "matched": false,
        "reason": ""
      }
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
    "library_notes": {
      "d3": "",
      "google_charts": "",
      "vega_lite": ""
    }
  },
  "chart_mapping": {},
  "data_type_reasoning": "",
  "limitations": []
}
```

Selection:

```json
{{SELECTION}}
```

Schema fragment:

```json
{{SCHEMA_FRAGMENT}}
```
