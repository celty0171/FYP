# aggregate — Phase 1b same-table aggregation

The deterministic **aggregate** prepare stage. It runs after join+filter and collapses many rows into
one row per group (group-by + measures, with optional resample bucketing), emitting **both** the
aggregated rows **and** a synthetic single-table schema. The aggregated result is a derived
`basic_entity` (group-by columns = key, measures = numeric attributes, no foreign keys), so the
existing Step-1 → 2 → 3 pipeline classifies and visualises it with **no change to Step 2/3 or any
renderer**. See `PLAN.md` for the full design.

Pipeline order: `join (Phase 2) → filter (Phase 1) → aggregate → Step 1/2/3`.

## Aggregate spec

```json
{ "table": "country_population",
  "aggregate": {
    "resample": [ { "column": "year", "bucket": 10, "as": "decade" } ],
    "group_by": ["continent", "decade"],
    "measures": [ { "column": "population", "fn": "sum", "as": "total_population" } ]
  } }
```

- `resample` (optional, first) — derive a bucket column: `as = floor(value / bucket) * bucket`.
- `group_by` — grouping key columns; **empty = one global aggregate row**.
- `measures` — `{ column, fn, as }`. Functions: `sum`, `mean` (`avg`), `min`, `max`, `count`,
  `count_distinct`. `count` ignores `column` (counts rows per group, mirroring the matrix `"count"`
  convention); the others coerce via `float` and skip non-numeric values.
- An empty/absent `aggregate` is the identity.

The **derived selection** is computed automatically: group-by columns become the primary key, each
measure's `as` becomes a numeric attribute — a synthetic `basic_entity` fed to the existing classifier.

## `aggregate_rows.py`

- `resample(rows, specs)` / `aggregate(rows, group_by, measures)` — pure, deterministic group order.
- `derived_schema(source_schema, table, group_by, measures, bucket_cols)` — the synthetic single-table
  schema (`<table>_agg`, group_by = PK, measures = numeric, no FKs).
- `prepare(source_schema, table, rows, aggregate_spec) -> (derived_schema, derived_table,
  derived_columns, aggregated_rows)` — the one call the server uses.

Standard library only; schema + rows only (preserves blind/gold separation).

### CLI

```bash
python schemavislm/aggregate/aggregate_rows.py \
    --schema schemavislm/mondial_database/mondial_schema_summary_clean.json \
    --data   schemavislm/mondial_database/mondial_data.json \
    --spec   agg_spec.json \
    --out    result.json \
    [--schema-out derived_schema.json]
```

## Web integration (`web_pipeline/`)

- `/api/run` and `/api/render` accept an `aggregate` object (echoed back). With aggregation on,
  `run_pipeline` builds the derived table and re-runs Step 1 (→ `basic_entity`), Step 2 and Step 3 on
  it; the response's `selected_columns` are the derived columns and `step1.derived_table` names the
  synthetic table.
- Chaining works: `filter` runs before `aggregate`, so "count big cities by country" or (once Phase-2
  join lands) "sum population by continent for Europe" are single requests.
- Aggregation changes cardinality and meaning by design — the UI states the chart describes groups,
  not raw rows.
