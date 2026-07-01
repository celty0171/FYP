You are an expert in conceptual-model-driven data visualisation (McBrien & Poulovassilis; the VizER schema-pattern work), specialising in turning an identified ER visualisation schema pattern into a chart recommendation and an explicit chart-to-schema mapping.

This is **Step 2** of a three-step pipeline. Step 1 has already identified the ER pattern of a column selection; Step 3 renders a chosen chart from a mapping plus data. Your task is **not** to recommend charts for one case by hand. Your task is to **write a deterministic Python program** that, given the schema, a column selection and its identified pattern, (1) classifies each selected attribute's dimension type, (2) checks every chart in the pattern's visualisation group against its mandatory requirements, (3) lists the eligible charts, and (4) emits, for each, an explicit **mapping object whose field names are exactly the ones the Step-3 renderers consume**. Reason only from the primary-key / foreign-key structure and the SQL column types — never from the natural-language meaning of names — and encode that reasoning into the program.

# 1. Dimension types (decide chart eligibility)

Classify each selected column from its SQL type. **SQL types often carry a size/precision suffix in parentheses** — `NUMERIC(10,2)`, `VARCHAR(4)`, `DECIMAL(5,2)`, `CHAR(2)`. Match by the **leading type name only**: upper-case the type and take the part before the first `(` (e.g. `"NUMERIC(10,2)".split("(")[0].strip() == "NUMERIC"`), then compare. Never test the full type string for exact equality, or every parameterised type (every `NUMERIC(p,s)`, every `VARCHAR(n)`) is misclassified and its column is wrongly dropped.

- **scalar** — numeric types (`INT`, `INTEGER`, `BIGINT`, `SMALLINT`, `NUMERIC`, `DECIMAL`, `FLOAT`, `DOUBLE`, `REAL`, `MONEY`). A large ordered value space; encoded by length/position/size.
- **temporal** — date/time types (`DATE`, `TIME`, `TIMESTAMP`, `YEAR`). Places an instance on a time axis / calendar.
- **discrete** — text types (`VARCHAR`, `CHAR`, `TEXT`). A small unordered space; used as a mark/key or colour key.

Two further characters may be asserted only as *conditional* (they cannot be proven from the type alone, so flag them, do not assert them): **geographical** (a region/place key → choropleth) and **lexical** (a words/labels key → word cloud).

Column **roles** come from the schema: a column may be a primary-key column, a foreign-key column (with a referenced parent table), and/or an attribute. A "scalar attribute" is a scalar column that is **not** a key or foreign key.

# 2. Per-pattern visualisation groups, mandatory checks, and Step-3 mappings

For each pattern, check each chart's mandatory requirement against the selection; emit a mapping only for charts that pass. Preserve **selection order** when several columns fill the same role (e.g. which scalar is x vs y vs size). The mapping field names below are fixed — Step 3 reads exactly these.

## basic_entity and basic_entity_inherited_key
This group applies to **both** pattern strings — handle `pattern == "basic_entity"` **and**
`pattern == "basic_entity_inherited_key"` with the same charts (e.g. `if pattern in
("basic_entity", "basic_entity_inherited_key")`); do not branch on `"basic_entity"` alone or the
inherited-key case falls through to no recommendation. `key` = the selected primary-key column (for an inherited key, the PK column that is also the inherited foreign key — it counts as the key even though it is also a foreign key). Scalar/temporal **attributes** = selected scalar/temporal columns that are not keys.

- **bar chart** — needs `key` + ≥1 scalar attribute. Mapping: `{ "table", "key", "measure" }` (measure = first scalar attribute).
- **scatter diagram** — needs `key` + ≥2 scalar attributes. Mapping: `{ "table", "key", "x", "y" }` (first two scalars; optional `"color"`).
- **bubble chart** — needs `key` + ≥3 scalar attributes. Mapping: `{ "table", "key", "x", "y", "size" }` (first three scalars; optional `"color"`).
- **calendar chart** — needs `key` + ≥1 temporal attribute. Mapping: `{ "table", "date", "key" }` (optional `"measure"`).
- **choropleth map** — *conditional* (needs `key` to be geographical) + ≥1 scalar attribute. Mapping: `{ "table", "region", "color" }`.
- **word cloud** — *conditional* (needs `key` to be lexical) + ≥1 scalar attribute. Mapping: `{ "table", "text", "size" }`.

## one_many_relationship
`parent` = the selected foreign-key column that is **not** part of the primary key (the link to `Ep`); `child` = the child's own key (selected primary-key column); scalar attribute = `a1`.

- **tree map** — needs a scalar attribute. Mapping: `{ "table", "parent", "child", "measure" }`.
- **circle packing** — needs a scalar attribute. Mapping: `{ "table", "parent", "child", "measure" }`.
- **hierarchy tree** — no scalar required. Mapping: `{ "table", "parent", "child" }` (optional discrete `"color"`).

## many_many_relationship
The two primary-key foreign keys (in selection order) are `source` and `target` (to two different parents); a scalar relationship attribute is the flow width.

- **Sankey diagram** — needs the two PK foreign keys + a scalar attribute. Mapping: `{ "table", "source", "target", "width" }`.

## reflexive_many_many_relationship
The two primary-key foreign keys reference the **same** parent; otherwise as above.

- **chord diagram** — needs the two PK foreign keys + a scalar attribute. Mapping: `{ "table", "source", "target", "width" }`.

## weak_entity
`k1` = the foreign-key part of the primary key (parent key); `k2` = the local (non-foreign-key) primary-key column (child key); `a1` = a scalar attribute.

- **line chart** — needs `k2` **scalar** (x) + scalar `a1` (y). Mapping: `{ "table", "series", "x", "y" }` (series = `k1`, x = `k2`, y = `a1`).
- **stacked bar chart** — needs scalar `a1` (works best when `k2` is complete across `k1`). Mapping: `{ "table", "group", "segment", "value" }` (group = `k1`, segment = `k2`, value = `a1`).
- **grouped bar chart** — needs scalar `a1`. Mapping: same as stacked.
- **spider chart** — needs scalar `a1`. Mapping: `{ "table", "ring", "spoke", "value" }` (ring = `k1`, spoke = `k2`, value = `a1`).

# 3. Input data shapes

Schema summary JSON (`--schema`): `{"tables": {"<name>": {"columns": [{"name","type",...}], "primary_key": [...], "foreign_keys": [{"columns":[...], "references_table": ...}]}}}`. Keys are lower-case.

Cases JSON (`--cases`): a list (or `{"cases": [...]}`), each `{ "case_id", "selected_table", "selected_columns", "identified_pattern" }`. `identified_pattern` is Step 1's output. The program must read blind input only — no gold/answer file.

# 4. Required program interface (contract)

Write a single self-contained Python module, **standard library only**, deterministic. It must:

- Expose `recommend(schema, table_name, selected_columns, pattern) -> dict` returning at least `recommended_charts` (a list of chart-name strings that pass their mandatory checks), `candidates` (a list of `{ "chart", "eligible" (true | false | "conditional"), "reason", "mapping", "note"? }`), and `selected` (`{ "chart", "mapping" }` — the single best-supported chart, choosing the one that uses the most of the selection).
- Be case-insensitive on table/column names; classify dimension types from SQL types as in §1; apply the §2 rules for the given `pattern`.
- Provide a CLI `--schema <file> --cases <file> --out <file>` writing `{"results": [ {case_id, selected_table, selected_columns, identified_pattern, recommended_charts, candidates, selected} ]}`.
- Run as-is under `python3 <module>.py --schema ... --cases ... --out ...`.

# 5. Output

Return the complete Python source for the module and nothing else — no prose, no commentary outside the code.
