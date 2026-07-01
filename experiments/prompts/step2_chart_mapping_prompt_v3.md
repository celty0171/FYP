You are an expert in conceptual-model-driven data visualisation (McBrien & Poulovassilis; the VizER schema-pattern work), specialising in turning an identified ER visualisation schema pattern into a chart recommendation and an explicit chart-to-schema mapping.

This is **Step 2** of a three-step pipeline. Step 1 has already identified the ER pattern of a column selection; Step 3 renders a chosen chart from a mapping plus data. Your task is **not** to recommend charts for one case by hand. Your task is to **write a deterministic Python program** that, given the schema, a column selection and its identified pattern, (1) classifies each selected attribute's dimension type, (2) checks every chart in the pattern's visualisation group against its mandatory requirements, (3) lists the eligible charts, and (4) emits, for each, an explicit **mapping object whose field names are exactly the ones the Step-3 renderers consume**. Reason only from the primary-key / foreign-key structure and the SQL column types — never from the natural-language meaning of names — and encode that reasoning into the program.

# 0. What the schema can and cannot prove

Decide chart eligibility from two things only: the **roles** of the selected columns (primary key, foreign key + referenced parent, plain attribute) and their **SQL data types**. These are structural facts in the schema.

Some properties the paper relies on are **properties of the data, not of the schema**, so they cannot be proven from the schema or selection alone. **Flag** them; never silently assert or deny them:

- **geographical** — a key that denotes a region/place (enables the choropleth map).
- **lexical** — a key that denotes words/labels (enables the word cloud).
- **completeness** (weak entity) — whether each parent key `k1` carries the same, or almost the same, set of child-key `k2` values. The paper makes this a **mandatory check for the stacked bar and spider charts** (pattern_notes: "Stacked bar and spider chart work best when `k2` values are complete or nearly complete across `k1` values"). It depends on the actual rows, so — unlike geographical/lexical — it cannot be read off the schema; the program must **measure it from the data** (see §2, weak_entity).

Geographical and lexical cannot be proven at all, so they gate their charts as **conditional** (see §2). Completeness *can* be measured, from the data rows the program is given at run time, so it is a **hard gate**: the stacked bar and spider charts are recommended **only when the data is (near-)complete**. Reading the data rows does not break the blind/gold separation — these are the same instance rows Step 3 renders, not the gold pattern/answer file. When no data is supplied the program cannot assert completeness and downgrades those two charts to **conditional**.

# 1. Dimension types (decide chart eligibility)

Classify each selected column from its SQL type. **SQL types often carry a size/precision suffix in parentheses** — `NUMERIC(10,2)`, `VARCHAR(4)`, `DECIMAL(5,2)`, `CHAR(2)`. Match by the **leading type name only**: upper-case the type and take the part before the first `(` (e.g. `"NUMERIC(10,2)".split("(")[0].strip() == "NUMERIC"`), then compare. Never test the full type string for exact equality, or every parameterised type (every `NUMERIC(p,s)`, every `VARCHAR(n)`) is misclassified and its column is wrongly dropped.

- **scalar** — numeric types (`INT`, `INTEGER`, `BIGINT`, `SMALLINT`, `NUMERIC`, `DECIMAL`, `FLOAT`, `DOUBLE`, `REAL`, `MONEY`). A large ordered value space; encoded by length/position/size.
- **temporal** — date/time types (`DATE`, `TIME`, `TIMESTAMP`, `YEAR`). Places an instance on a time axis / calendar; also an **ordered** axis.
- **discrete** — text types (`VARCHAR`, `CHAR`, `TEXT`). A small unordered space; used as a mark/key or colour key.

Column **roles** come from the schema: a column may be a primary-key column, a foreign-key column (with a referenced parent table), and/or an attribute. A "scalar attribute" is a scalar column that is **not** a key or foreign key.

# 2. Per-pattern visualisation groups, mandatory checks, and Step-3 mappings

For each pattern, check each chart's mandatory requirement against the selection; emit a mapping only for charts that pass. Preserve **selection order** when several columns fill the same role (e.g. which scalar is x vs y vs size). The mapping field names below are fixed — Step 3 reads exactly these.

## basic_entity and basic_entity_inherited_key
This group applies to **both** pattern strings — handle `pattern == "basic_entity"` **and** `pattern == "basic_entity_inherited_key"` with the same charts (e.g. `if pattern in ("basic_entity", "basic_entity_inherited_key")`); do not branch on `"basic_entity"` alone or the inherited-key case falls through to no recommendation. `key` = the selected primary-key column (for an inherited key, the PK column that is also the inherited foreign key — it counts as the key even though it is also a foreign key). Scalar/temporal **attributes** = selected scalar/temporal columns that are not keys.

- **bar chart** — needs `key` + ≥1 scalar attribute. Mapping: `{ "table", "key", "measure" }` (measure = first scalar attribute).
- **scatter diagram** — needs `key` + ≥2 scalar attributes. Mapping: `{ "table", "key", "x", "y" }` (first two scalars; optional `"color"` = first discrete attribute).
- **bubble chart** — needs `key` + ≥3 scalar attributes. Mapping: `{ "table", "key", "x", "y", "size" }` (first three scalars; optional `"color"`).
- **calendar chart** — needs `key` + ≥1 temporal attribute. Mapping: `{ "table", "date", "key" }` (optional `"measure"` = first scalar attribute).
- **choropleth map** — *conditional* (needs `key` to be **geographical** — flag, do not assert) + ≥1 scalar attribute. Mapping: `{ "table", "region", "color" }`.
- **word cloud** — *conditional* (needs `key` to be **lexical** — flag, do not assert) + ≥1 scalar attribute. Mapping: `{ "table", "text", "size" }`.

## one_many_relationship
`parent` = the selected foreign-key column that is **not** part of the primary key (the link to `Ep`); `child` = the child's own key (selected primary-key column); scalar attribute = `a1`.

- **tree map** — needs a scalar attribute (area). Mapping: `{ "table", "parent", "child", "measure" }`.
- **circle packing** — needs a scalar attribute (area). Mapping: `{ "table", "parent", "child", "measure" }`.
- **hierarchy tree** — **no scalar required** (it is a node-link chart, not an area chart). Mapping: `{ "table", "parent", "child" }` (optional discrete `"color"` = first discrete attribute, used by Step 3 to colour the links).

## many_many_relationship and reflexive_many_many_relationship
Handle **both** pattern strings here (e.g. `if pattern in ("many_many_relationship", "reflexive_many_many_relationship")`). Both are a relationship table whose two primary-key foreign keys (in selection order) are `source` and `target`, plus a scalar relationship attribute `a1` that gives the flow / ribbon width. The patterns differ **only** in whether the two foreign keys reference **two different** parents (`many_many_relationship`) or the **same** parent (`reflexive_many_many_relationship`).

Both charts apply to **both** patterns — a relationship between two instance sets can be drawn either as a left-to-right flow (Sankey) or as ribbons around a circle (chord); the reflexive case is just the special case where the two sets coincide. So recommend **both** charts whenever the mandatory check passes; do not gate either chart on which of the two patterns it is.

- **Sankey diagram** — needs the two PK foreign keys + a scalar attribute. Mapping: `{ "table", "source", "target", "width", "pattern" }`.
- **chord diagram** — needs the two PK foreign keys + a scalar attribute. Mapping: `{ "table", "source", "target", "width", "pattern" }`.

Add `"pattern"` (the identified pattern string) to both mappings so the Step-3 renderer can frame the two instance sets correctly (namespacing the two sides for `many_many`, sharing one node set for `reflexive`). `"pattern"` is the only field that differs between the two patterns; `source`/`target`/`width` are filled identically. For `selected`, prefer the **Sankey diagram** for `many_many_relationship` (two distinct sets read most clearly as a left-to-right flow) and the **chord diagram** for `reflexive_many_many_relationship` (one shared set reads most clearly around a circle).

## weak_entity
`k1` = the foreign-key part of the primary key (parent key); `k2` = the local (non-foreign-key) primary-key column (child key); `a1` = a scalar attribute. The paper frames a weak entity as a compound key `k1 × k2` plus `a1`; all charts pivot the rows by `k1 × k2`.

**Completeness gate — measured from the data (read §0).** The paper's mandatory check makes completeness a **requirement** for the stacked bar and spider charts: each `k1` should carry the same, or almost the same, set of `k2` values. Measure it deterministically from the rows of the selected table:

- let `K1` = the distinct non-null `k1` values, `K2` = the distinct non-null `k2` values, and `P` = the distinct `(k1, k2)` pairs that actually occur in the rows;
- `density = |P| / (|K1| * |K2|)` — this equals the average fraction of the `k2` universe that each `k1` covers, i.e. how close every `k1` is to carrying the whole `k2` set;
- the selection is **(near-)complete** when `density >= NEAR_COMPLETE`, a named constant (default `0.6`). Guard the empty cases (`|K1| == 0` or `|K2| == 0` → not complete).

Apply this as a **hard gate** for two charts only: recommend the **stacked bar** and **spider** charts only when `a1` is scalar **and** the data is (near-)complete. If the data is incomplete, set `eligible: false` with a reason that names the measured `density` and the `NEAR_COMPLETE` threshold. If no data was supplied to the program, set `eligible: "conditional"` with a note that completeness is unverified. The line and grouped charts are **not** completeness-gated — the paper names only the stacked bar and spider charts in that mandatory check.

- **line chart** — hard check: `k2` is **scalar** (a numeric, ordered x-axis; a **temporal** `k2` also forms an ordered x-axis and is acceptable) **and** `a1` is scalar (y). Not completeness-gated (it needs an ordered `k2`, which is a schema check, not a data one). Mapping: `{ "table", "series", "x", "y" }` (series = `k1`, x = `k2`, y = `a1`). An XY variant may add a second scalar attribute `a2`; keep the base mapping and, if present, you may add `"y2"`.
- **stacked bar chart** — hard check: scalar `a1` **and** (near-)complete data (gate above). Step 3 still keeps the shared-core `k2` segments and folds the rest into an `(other)` band, but the chart is only **recommended** when the data is complete. Mapping: `{ "table", "group", "segment", "value" }` (group = `k1`, segment = `k2`, value = `a1`).
- **grouped bar chart** — hard check: scalar `a1` (**not** completeness-gated). `note`: a side-by-side **comparison** of `a1` across `k2`; Step 3 keeps the comparable-core `k2` and the most-complete `k1`, and drops the long tail (no `(other)` fold — that suits only the composition chart). Mapping: same field names as stacked: `{ "table", "group", "segment", "value" }`.
- **spider chart** — hard check: scalar `a1` **and** (near-)complete data (gate above). `note`: works best with a small `k2`; Step 3 caps to the top rings (`k1`) and spokes (`k2`). Mapping: `{ "table", "ring", "spoke", "value" }` (ring = `k1`, spoke = `k2`, value = `a1`).

If several weak charts are eligible they all use the same three columns; for `selected`, prefer the line chart when `k2` is ordered (scalar/temporal), since an ordered x makes the strongest single view; otherwise fall back to the first eligible chart in the order above. This keeps `selected` deterministic.

# 3. Input data shapes

Schema summary JSON (`--schema`): `{"tables": {"<name>": {"columns": [{"name","type",...}], "primary_key": [...], "foreign_keys": [{"columns":[...], "references_table": ...}]}}}`. Keys are lower-case.

Cases JSON (`--cases`): a list (or `{"cases": [...]}`), each `{ "case_id", "selected_table", "selected_columns", "identified_pattern" }`. `identified_pattern` is Step 1's output. The program must read blind input only — no gold/answer file.

Data JSON (`--data`, **optional**): the grouped database `{"tables": {"<name>": [ {row…}, … ]}}` (or a flat row array for one table). Used **only** to measure weak-entity completeness (§2); the table is selected by `selected_table`. These are instance rows, not gold answers, so reading them respects the blind/gold separation. When `--data` is omitted, the completeness-gated charts (stacked bar, spider) are reported as `conditional`.

# 4. Required program interface (contract)

Write a single self-contained Python module, **standard library only**, deterministic. It must:

- Expose `recommend(schema, table_name, selected_columns, pattern, rows=None) -> dict` returning at least `recommended_charts` (a list of chart-name strings that pass their mandatory checks — i.e. `eligible` is `true`; do **not** list `conditional` charts here), `candidates` (a list of `{ "chart", "eligible" (true | false | "conditional"), "reason", "mapping", "note"? }` — emit a `mapping` for `true` and `conditional` charts, and a `note` wherever §0/§2 calls for one), and `selected` (`{ "chart", "mapping" }` — the single best-supported chart per §2, choosing the one that uses the most of the selection, with the weak-entity tie-break above). `rows` is the selected table's row list, used **only** to measure weak-entity completeness (§2); when `rows is None` the completeness-gated charts (stacked bar, spider) are returned as `conditional`.
- Be case-insensitive on table/column names; classify dimension types from SQL types as in §1; apply the §2 rules for the given `pattern`.
- Provide a CLI `--schema <file> --cases <file> --out <file>` plus an **optional** `--data <file>`. When `--data` is given, select each case's rows by `selected_table` from the grouped database and pass them to `recommend` so the completeness gate is live; when it is omitted, call `recommend` with `rows=None`. Write `{"results": [ {case_id, selected_table, selected_columns, identified_pattern, recommended_charts, candidates, selected} ]}`.
- Run as-is under `python3 <module>.py --schema ... --cases ... --out ... [--data ...]`.

# 5. Output

Return the complete Python source for the module and nothing else — no prose, no commentary outside the code.
