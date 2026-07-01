# Mondial Pattern Prompt — Conceptual-Modelling Grounding (McBrien & Poulovassilis)

You are evaluating a DATA-FIRST column selection from the Mondial relational database.

Your task is grounded in the conceptual-modelling approach of McBrien and Poulovassilis,
"Towards Data Visualisation based on Conceptual Modelling and Schema Transformations"
(AutoMed Technical Report 39). Reason about the *conceptual model* implied by the schema,
not about the natural-language meaning of table or column names.

## 1. What a visualisation is, conceptually

In this approach a visualisation is produced by mapping conceptual-schema constructs onto
graphic elements:

- Each instance of an **entity** is associated with one or more graphic elements — *marks*
  (points, lines, areas) and *channels* (colour, length, shape, coordinate, size, etc).
- The value of an **attribute**, or the **participation of an entity in a relationship**,
  is associated with a *dimension* of the visualisation.

Choosing a visualisation therefore means finding a sub-graph of the database schema that
matches one of a small set of **visualisation schema patterns**. This is a subgraph-matching
problem: identify which pattern's entities, keys, attributes and relationship cardinalities
are present in the selected columns.

## 2. Dimension types (these decide chart eligibility)

Classify every selected attribute as one of two dimension types:

- **scalar dimension**: a large number of distinct values with a natural numeric ordering —
  integers, floats/decimals, and temporal values (dates, years, timestamps). Represented by a
  channel (length, position, size, colour spectrum). Infer scalar from SQL numeric/temporal
  types (e.g. INTEGER, NUMERIC, DECIMAL, FLOAT, DATE).
- **discrete dimension**: a relatively small number of distinct values, possibly unordered —
  used to choose a mark or vary a channel via a colour key. Infer discrete from short
  text/code types and identifier-like columns.

A dimension may additionally carry a real-world character that enables specific charts:
- **geographical** — a key interpretable as a region/place (enables choropleth maps);
- **temporal** — a date/year value (enables calendar charts, time axes);
- **lexical** — a key interpretable as words/labels (enables word clouds).

Only assert geographical/temporal/lexical when the column type and role genuinely support it.

## 3. Cardinality drives the pattern

Identify the pattern from primary-key (PK) and foreign-key (FK) structure, which encode the
relationship cardinalities of the conceptual model. The six patterns (Figure 5 of the paper)
are, using generic variables (E entity, k key, a attributes, R relationship):

- `basic_entity`: an entity `E` identified by key `k` with attributes `a1, a2, …`, with no
  selected foreign-key dependency.
- `basic_entity_inherited_key`: the entity's key is *inherited* — the whole primary key is a
  foreign key from a single parent entity, and there is no local primary-key column. Each such
  instance corresponds to exactly one parent instance (a subset/specialisation of the parent),
  so it is treated as a basic entity, not a weak entity.
- `weak_entity`: a compound key in which one part `k1` is a foreign key to a single parent
  entity (the relationship `R` is 1:1 on the weak side, 0:N on the parent side) and the
  remaining part `k2` is a local key that identifies a tuple *within* the set of tuples sharing
  a value of `k1`.
- `one_many_relationship`: a hierarchical relationship `R` (0:N on the parent / "many" side,
  1:1 on the child) in which the selected columns include a foreign key to a parent entity that
  is **not** part of the table's primary key. The parent is `Ep`, the child is `Ec`.
- `many_many_relationship`: a relationship table `R` whose primary key consists of two foreign
  keys (0:N : 0:N) referencing **two different** parent entities `E1`, `E2`; the data governing
  the visualisation is held as attributes of `R`.
- `reflexive_many_many_relationship`: the special many-many case where both primary-key foreign
  keys reference the **same** parent entity `E`.

Apply this decision order; take the first matching rule and justify it with PK/FK evidence:

1. If the full primary key has ≥2 columns and every primary-key column is a foreign key:
   `many_many_relationship` when the foreign keys reference different parents, else
   `reflexive_many_many_relationship` when they reference the same parent.
2. Else if the whole primary key is one inherited foreign key from a single parent and there is
   no local primary-key column: `basic_entity_inherited_key`.
3. Else if the primary key is compound and mixes foreign-key column(s) with local key
   column(s): `weak_entity`.
4. Else if a selected column is a foreign key that is not part of the primary key:
   `one_many_relationship`.
5. Else: `basic_entity`.

Boundary checks (decide by key *composition*, not by names):

- Distinguish inherited-key basic entity from weak entity by whether *every* primary-key column
  is a foreign key (inherited-key basic) or the key *combines* foreign-key and local columns
  (weak).
- Do not call a weak entity `one_many_relationship` just because it has a parent foreign key:
  if that foreign key is *part of the primary key* and a local key column remains, it is
  `weak_entity`.
- Do not call a selection `basic_entity` just because the table has its own key and attributes:
  if a selected foreign key lies *outside* the primary key, it is `one_many_relationship`.
- For two-foreign-key primary keys, check whether the two keys reference the *same* parent
  (reflexive) or *different* parents (plain many-many).

## 4. Recommend visualisations by matching the pattern's eligibility

After identifying the pattern, recommend only the charts whose mandatory variables can actually
be mapped to selected columns of the right dimension type. Do not list every chart in the group.
Cardinality bounds below (|k| = number of distinct key values) are aesthetic guidance from the
paper, not hard cut-offs.

Basic entity:
- bar chart — key `k`, one scalar `a1` (|k| up to ~100).
- calendar chart — a temporal `a1` (optional scalar `a2` for colour).
- scatter chart — two scalar attributes `a1`, `a2` (optional `a3` colour).
- bubble chart — three scalar attributes `a1`, `a2`, `a3` (optional `a4` colour).
- choropleth map — `k` geographical, scalar/colourable `a1`.
- word cloud — `k` lexical, scalar `a1` (optional `a2` colour).

Weak entity (`k1` parent key, `k2` local key, `a1` scalar measure):
- line chart — scalar `k2` on the x-axis, scalar `a1` on the y-axis (optional `a2`); does not
  require completeness.
- stacked bar chart — scalar `a1`; works best when `k2` values are *complete* across `k1`.
- grouped bar chart — scalar `a1`; does not require completeness.
- spider chart — scalar `a1`; best with complete `k2` across `k1` (|k1| ~3..10).

One-many relationship (`Ep` parent, `Ec` child, `kp`/`kc` keys, `a1` scalar child measure):
- treemap — requires scalar `a1` (optional `a2` colour).
- hierarchy tree — needs only parent/child keys (optional discrete `a1` to colour links).
- circle packing — requires scalar `a1` (optional `a2` colour).

Many-many relationship (`E1`, `E2` parents, `k1`/`k2` foreign keys, `a1` scalar relationship
attribute):
- sankey diagram — non-reflexive links, scalar `a1` as flow width; source = `k1`, target =
  `k2`, width = `a1` (optional `a2` colour).

Reflexive many-many relationship (`E` single parent, `k1`/`k2` foreign keys, `a1` scalar
relationship attribute):
- chord diagram — points around a circle are instances of the single entity `E`; scalar `a1`
  sets connection width (optional `a2` colour).

## 5. Transformations (when the schema must be conformed to a pattern)

Where the raw selection does not directly fit the chosen chart, note the schema transformation
required (as in Section 4 of the paper), for example:
- **pivot** — turn instances of an entity (e.g. distinct values of a temporal key) into separate
  columns so two instances can be compared on one mark;
- **denormalise / roll-up / drill-down** — move relationship attributes into an entity, or
  aggregate child instances up to a parent, to expose the sub-graph a chart needs.

State such needs in `required_transformations`; leave empty when none is needed.

## 6. Output

Return JSON only, with exactly this shape:

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

Use `cardinality_reasoning` to explain the relationship cardinalities you inferred from the
PK/FK structure, and `data_type_reasoning` to record which selected columns you treated as
scalar vs discrete (and any geographical/temporal/lexical character) and why.

Selection:

```json
{{SELECTION}}
```

Schema fragment:

```json
{{SCHEMA_FRAGMENT}}
```
