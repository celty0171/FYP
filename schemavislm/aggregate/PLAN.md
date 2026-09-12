# Phase 1b — Same-table aggregation (group-by / resample): implementation plan

## Goal

Filtering (Phase 1) subsets rows but never changes what a row *means*. Aggregation does: "total
`population` **by** `continent`", "**average** GDP per `continent`", "population resampled **by
decade**". Each collapses many rows into one row per group. This unlocks the summary charts a raw table
cannot show (a bar of population per continent instead of 2278 country-year points).

Aggregation is deeper than filtering because it **produces a new logical table**: the group-by columns
become its key, the aggregates become its measures, and all relationships dissolve. The clean way to
handle that in this project's paradigm is to treat the aggregated result as a **derived
`basic_entity`** and run the *same* Step-1 → 2 → 3 pipeline on it.

## Design principle: aggregate to a derived basic_entity, then re-run the pipeline

Aggregation is a deterministic *prepare* stage that runs **after** join and filter and emits **two**
things — the aggregated rows **and** a synthetic mini-schema describing them:

```
selection = { table, columns, joins, filters, aggregate }
      │
      ▼
[ join ]    (Phase 2, optional)  enrich with foreign columns
      │
      ▼
[ filter ]  (Phase 1)            subset the rows
      │
      ▼
[ aggregate ]  group_by + measures  →  aggregated rows  +  synthetic schema (a derived table)
      │                                     │
      │                                     └─► Step 1 classifies the DERIVED table   → basic_entity
      ▼
   Step 2 recommends on the derived selection (group keys + measures)   (unchanged program)
      ▼
   Step 3 render(mapping, aggregated rows)                              (unchanged renderers)
```

Verified premise: a derived table of *group-by key(s) + numeric measures with no foreign keys*
classifies as **`basic_entity`** under the current Step-1 classifier — for both a single key
(`continent`) and a composite key (`continent, decade`). So "sum population by continent" becomes a
`basic_entity {key: continent, measure: total_population}` → **bar chart**, entirely through the
existing programs. No renderer or Step-2 change is needed; the whole feature is the aggregate stage plus
a synthetic schema.

Aggregation runs **after** filter (subset first, then summarise the subset) and **after** join (so a
group-by can use a joined column such as `continent`). This ordering is what makes "join continent →
filter Europe → sum population by continent" a single request.

## Aggregate spec (the contract)

```json
{
  "table": "country_population",
  "aggregate": {
    "resample": [ { "column": "year", "bucket": 10, "as": "decade" } ],
    "group_by": ["continent", "decade"],
    "measures": [
      { "column": "population", "fn": "sum", "as": "total_population" }
    ]
  }
}
```

- `resample` (optional, runs first) — derive a bucketed column from a scalar/temporal one:
  `as = floor(value / bucket) * bucket`. Adds a column usable in `group_by` (e.g. `decade`). Deterministic.
- `group_by` — the grouping key columns. **Empty list = global aggregate** (one output row).
- `measures` — one or more `{ column, fn, as }`. Functions: `sum`, `mean` (alias `avg`), `min`, `max`,
  `count`, `count_distinct`. `count` ignores `column` (counts rows per group); the others coerce via
  `float` and skip non-numeric values.
- An empty/absent `aggregate` is the identity — the pipeline behaves exactly as before.

**Derived selection** (computed by the server, not the user): the derived table's columns are the
`group_by` columns (its **primary key**, types carried over from the source columns; a bucket column is
integer) **plus** each measure's `as` (numeric, non-key). This synthetic schema + these columns are
what Step-1/2/3 consume.

## Deliverables

### 1. `schemavislm/aggregate/aggregate_rows.py` (new, std-lib only)

The deterministic aggregation program (the LLM-as-compiler artefact for this stage). Public functions:

- `resample(rows, specs) -> rows'` — add each bucket column; pure, order-preserving.
- `aggregate(rows, group_by, measures) -> list[dict]` — group and reduce; **deterministic group order**
  (sorted by the group-key tuple); one row per group with the group keys + each `as` measure. Global
  aggregate when `group_by == []`. Never mutates input.
- `derived_schema(source_schema, table, group_by, measures, bucket_cols) -> (schema, columns)` — build
  the synthetic single-table schema (group_by = PK, measures = numeric attrs, **no foreign keys**) and
  the derived column list, so the existing Step-1 classifier can run on the result.
- `prepare(source_schema, table, rows, aggregate_spec) -> (derived_schema, derived_table, derived_columns, agg_rows)`
  — the one call the server uses: resample → aggregate → build synthetic schema. Returns everything the
  downstream steps need.
- CLI `--schema --data --spec --out` mirroring `apply_filters.py` / `join_tables.py`.

No gold knowledge; schema + rows only (preserves blind/gold separation).

### 2. `schemavislm/web_pipeline/server.py` (edit)

- Load the module: `AGG = _load(EXP / "aggregate" / "aggregate_rows.py", "prepare_aggregate")`.
- In `run_pipeline`, after join+filter produce `rows`, branch on `aggregate`:
  - **with aggregate:** `dschema, dtable, dcols, arows = AGG.prepare(SCHEMA, table, rows, aggregate)`;
    then run `STEP1.classify_selection(dschema, dtable, dcols)`, `STEP2.recommend(dschema, dtable,
    dcols, pattern, rows=arows)`, and `render_chart(selected.chart, selected.mapping,
    data={"tables": {dtable: arows}})`. The mapping's `table` is the derived table name.
  - **without aggregate:** unchanged Phase-1/2 path.
- `/api/run` and `/api/render` bodies gain an `aggregate` object (echoed back). For `/api/render` the
  server rebuilds the aggregated `data` view the same way so a pill click re-renders the aggregate.
- Response reports the derived pattern/columns so the UI shows what was actually classified.

### 3. `schemavislm/web_pipeline/index.html` (edit)

- A new **"Aggregate"** sub-panel: a group-by multiselect (over the table's + joined columns), a
  measures editor (column + function + optional alias; default `sum`), and an optional resample control
  (a numeric column + bucket size). Empty group-by/measures = aggregation off.
- Send `aggregate` through `/api/run` and every pill `/api/render`, alongside `joins`/`filters`.
- Show the derived pattern + a one-line "aggregated: sum(population) by continent" summary; make clear
  that with aggregation on, the chart describes groups, not raw rows.

### 4. `schemavislm/aggregate/README.md` (new)

Spec format, the six functions + resample, the CLI example, and the "aggregate → derived basic_entity →
re-run Step-1/2/3; renderers untouched" architecture line.

## Worked examples (acceptance)

| Base (+ join/filter) | Aggregate | Expected derived result |
|----------------------|-----------|--------------------------|
| `country_population` + join `continent` | `group_by continent, sum population` | `basic_entity {key: continent, measure: total_population}` → **bar chart**; ~6 rows |
| `country_population` | `resample year by 10 → decade; group_by decade, mean population` | `basic_entity {key: decade, measure: avg_population}` → bar/line; one row per decade |
| `country_population` + join `continent` + filter `Europe` | `group_by continent, sum population` | one row (Europe); global-ish summary of the filtered subset |
| `city` | `group_by country, count` | one row per country with a row count; `basic_entity` → bar |
| any | no aggregate | identical to Phase-1/2 (regression: identity) |

## Verification

1. **Aggregate correctness:** `aggregate` on known data — `sum population by continent` totals match a
   manual group-by; `count` equals group sizes; `mean` skips non-numeric; global aggregate
   (`group_by=[]`) yields exactly one row. Deterministic group order.
2. **Resample:** `year` bucket 10 maps 1994→1990, 2003→2000; grouping by the bucket column works.
3. **Derived classification:** `derived_schema` + Step-1 returns `basic_entity` for single and
   composite keys (already confirmed); Step-2 recommends bar/scatter/etc. with a mapping whose `table`
   is the derived table and whose fields match the derived columns.
4. **End-to-end (server):** `/api/run` with `aggregate` renders the summary chart from `arows`;
   `/api/render` keeps the aggregate on a pill click; identity (`aggregate` absent) is byte-identical to
   Phase-1. Chaining join→filter→aggregate produces the "sum population by continent for Europe" case.

## Design notes & risks

- **Composite-key derived tables** classify as `basic_entity` today, but a two-key summary is arguably a
  matrix/heatmap candidate (continent × decade). Phase 1b keeps it as `basic_entity` (bar/grouped bar);
  a richer "pivot → matrix" mapping is a later refinement, not part of this stage.
- **`count` without a numeric column** must never attempt numeric coercion — it counts rows, mirroring
  the matrix `"count"` fallback convention already in the codebase.
- **Aggregation changes cardinality by design** — unlike filtering, the row count and meaning change;
  the UI must state this so a user does not read grouped bars as raw instances.

## Invariants preserved

- Blind/gold separation: `aggregate_rows.py` reads schema + rows only; the synthetic schema carries **no
  pattern labels** — Step-1 still derives the pattern from structure.
- Std-lib only; CLI mirrors the existing scripts; a new sibling folder to `filter/` and `join/`.
- Step-2/3 programs and every renderer are **unchanged**; the feature is the aggregate stage plus a
  synthetic schema fed to the existing classifier. With `aggregate` absent, behaviour is exactly Phase-1.
