# Phase 1 — Same-table filtering: implementation plan

## Goal

Today the web front-end can only pick a **table** and a set of **columns**. That is too coarse for
real exploration: a user looking at `country_population` may want only `year ∈ [1990, 2020]`; a user
looking at `encompasses` may want only `continent = 'Europe'`. Phase 1 adds **same-table row
filtering** — a `WHERE`-style subset applied to the chosen relation's rows *before* the pipeline runs
— without touching the Step-1/2/3 contracts. Aggregation, resampling and cross-table joins are later
phases (see *Out of scope*).

## Design principle: a deterministic prepare layer, before Step 2

Filtering is a data transformation, so it must **not** live inside a renderer. It sits as a new
deterministic stage between "load the relation's rows" and "Step 2 measures the data":

```
selection = { table, columns, filters }
      │
      ▼
[ prepare ]  read DATA.tables[table]  →  apply(filters)  →  rows'
      │
      ├─►  Step 2 selector  measures density / N / symmetric on rows'   →  recommend + mapping
      │
      └─►  Step 3 renderer  render(mapping, rows')                      →  HTML
```

Two facts make this cheap and safe:

1. **Renderers need no change.** Each renderer reads its rows through
   `_rows_for(mapping, data)`, which returns `data["tables"][mapping["table"]]`. So the server just
   builds a *filtered view* `fdata = {"tables": {table: rows'}}` and passes `fdata` where it currently
   passes the global `DATA`. `render(mapping, rows')` then draws the subset.
2. **The selector already takes rows.** `STEP2.recommend(..., rows=rows')` already exists; feeding it
   the filtered rows means density/N are measured on the subset, so recommendations update for free
   (e.g. `encompasses` filtered to one continent may drop below `DENSE` and re-surface Sankey/chord as
   the top pick instead of the matrix). This is the emergent payoff of putting the filter *before*
   Step 2.

Filtering is placed **before** Step 2 deliberately — never after — because the whole §4 selector is
data-driven; measuring signals on the unfiltered relation would recommend the wrong chart for the
subset the user is actually looking at.

## Filter spec (the contract)

A single JSON object, produced by the UI, carried on `/api/run` and echoed back so pill clicks keep
the filter. Same-table only: `spec.table` always equals `mapping.table`.

```json
{
  "table": "country_population",
  "filters": [
    { "column": "year",       "op": "range", "min": 1990, "max": 2020 },
    { "column": "continent",  "op": "in",    "values": ["Europe", "Asia"] }
  ]
}
```

Operators for phase 1 (all are conjunctive — rows must satisfy **every** filter):

| op       | applies to            | semantics                                                        |
|----------|-----------------------|-----------------------------------------------------------------|
| `range`  | scalar / temporal     | keep rows with `min ≤ value ≤ max`; either bound optional        |
| `in`     | discrete (categorical)| keep rows whose value is in `values`                             |
| `eq`     | any                   | sugar for `in` with a single value                              |
| `not_null` | any                 | drop rows where the column is null/absent                        |

Rules: an empty `filters` array is a no-op (identity). A filter naming a column absent from a row
treats that row as **not matching** (safe default). Numeric/temporal comparisons coerce via `float()`;
a value that fails coercion does not match a `range`. Unknown `op` is ignored with a note rather than
erroring, so a forward-compatible UI never breaks the server.

## Deliverables

### 1. `experiments/filter/apply_filters.py` (new, std-lib only)

The deterministic prepare program — the LLM-as-compiler artefact for this stage (authored once, run
reproducibly; a GPT-authored sibling can follow later, as with Step 1/2). Public functions:

- `apply(rows, filters) -> list[dict]` — the conjunctive filter described above. Pure, order-preserving,
  never mutates input rows.
- `column_stats(rows, columns=None) -> dict` — one entry per column so the UI can build the right
  control **from data**, without hard-coding Mondial names:
  ```json
  {
    "year":       { "dim": "temporal", "min": 1950, "max": 2020, "count": 2278 },
    "continent":  { "dim": "discrete", "values": ["Africa","Asia","Europe", ...], "distinct": 6 },
    "population": { "dim": "scalar",   "min": 447, "max": 1.4e9, "count": 2278 }
  }
  ```
  `dim` is inferred from observed values (int/float → scalar; small integer year-like → temporal is
  optional, else scalar; string → discrete). Discrete columns list distinct values **only** up to a
  cardinality cap (`MAX_DISTINCT = 60`); above the cap, omit `values` and set `"high_cardinality": true`
  so the UI falls back to a free-text `contains`/no control. Numeric columns report `min`/`max` for
  range controls.
- CLI `--data <mondial_data.json> --spec <filter_spec.json> --out <rows.json>` mirroring the other
  scripts, so a filter can be applied and inspected offline and results are reproducible.

Keep this module free of any schema/gold knowledge — it operates purely on rows, preserving the
blind/gold separation invariant.

### 2. `experiments/web_pipeline/server.py` (edit)

- Load the module: `FILTER = _load(EXP / "filter" / "apply_filters.py", "prepare_filter")`.
- Add a helper `filtered_data(table, filters)` → `{"tables": {table: FILTER.apply(DATA.tables[table], filters)}}`.
- `run_pipeline(table, columns, filters)`:
  - `rows = filtered_data(table, filters)["tables"][table]`
  - **empty guard:** if `rows == []`, return a `step3 = {"available": False, "html": "no rows match the current filter"}` and empty recommendations, so the UI shows a clean message instead of a render error.
  - `STEP2.recommend(SCHEMA, table, columns, pattern, rows=rows)` (unchanged call, filtered rows).
  - `render_chart(selected.chart, selected.mapping, data=filtered_data(...))`.
  - include the applied `filters` in the response so the client can resend them on pill clicks.
- `render_chart(chart, mapping, data=DATA)` — add the optional `data` param (defaults to global `DATA`
  for backward compatibility); pass it to `mod._rows_for(mapping, data)`.
- `/api/run` body gains `filters`; `/api/render` body gains `table` + `filters` so a re-render keeps
  the same subset (build `fdata` from them, else fall back to `DATA`).
- New `GET/POST /api/column_stats` → given `table` (+ optional `columns`), return
  `FILTER.column_stats(DATA.tables[table], columns)` for the UI to build controls. Stats are computed
  on the **unfiltered** table so ranges/among-values stay stable as the user adjusts filters.

### 3. `experiments/web_pipeline/index.html` (edit)

- After a table is chosen (and on column change), `POST /api/column_stats` and render a new
  **"2. Filters"** sub-panel under the selection panel. One control per filterable column of the
  chosen table (independent of which columns are ticked for the visualisation, so a user can restrict
  to Europe without charting `continent`):
  - **scalar / temporal** → two number inputs (min / max) pre-filled with the column's data range (or a
    dual-handle slider).
  - **discrete, low-cardinality** → a checklist of distinct `values` (all checked = no filter).
  - **discrete, high-cardinality** → a free-text "contains" box (maps to a simple `in`/substring), or
    omit with a hint.
- Collect the non-default controls into a `filters` array; send it on `/api/run`, and store it in
  `last.filters` so each pill click (`/api/render`) resends `{ chart, mapping, table, filters }`.
- Show a one-line **active-filter summary** (e.g. `year 1990–2020 · continent ∈ {Europe, Asia}`) and a
  **Clear filters** button. No change to the `built` set or the pill logic.

### 4. `experiments/filter/README.md` (new)

Short usage note: the spec format, the four operators, the CLI example, and the "filter runs before
Step 2, renderers untouched" architecture line — so the folder is self-documenting alongside the
existing `results/*/SUMMARY.md` convention.

## Worked examples (acceptance)

| Selection | Filter | Expected effect |
|-----------|--------|-----------------|
| `country_population` (country, year, population) | `year range 1990–2020` | line/calendar renders only the 1990–2020 slice; row count drops from 2278 to the in-range subset |
| `encompasses` (country, continent, percentage) | `continent in {Europe}` | edges fall; Step-2 density recomputed on the subset; if it drops below `DENSE`, Sankey/chord become the top pick over the matrix — the recommendation *changes with the filter* |
| `encompasses` | no filter | identical to today (regression check: identity filter is a no-op) |
| any | filter matches nothing | UI shows "no rows match the current filter", no stack trace |

## Verification

1. **Unit (offline):** run `apply_filters.py --data mondial_data.json --spec <spec> --out /tmp/rows.json`
   for each worked example; assert row counts and that an empty `filters` reproduces the input exactly.
2. **Selector interaction:** call `STEP2.recommend(..., rows=<filtered>)` for the `encompasses` +
   Europe case and confirm `recommended_charts` / `selected` differ from the unfiltered run in the
   expected direction (density-driven).
3. **End-to-end (server):** `POST /api/column_stats` returns the right control metadata;
   `POST /api/run` with `filters` renders the subset; `POST /api/render` with `{table, filters}` keeps
   the subset on a pill click; empty-result guard shows the friendly message.
4. **Regression:** a run with no filters is byte-identical to the current behaviour (renderers and the
   selector unchanged when `filters == []`).

## Out of scope (later phases)

- **Aggregation / resampling** (group-by continent, sum population, 5-year buckets) — changes "what one
  row means"; needs its own spec section and selector-awareness.
- **Cross-table filtering** (e.g. `country_population` "by continent", which lives in `encompasses`) —
  requires an FK-path join to attach the foreign column first, then reduces to a same-table filter.
- **Pattern re-classification from a subset** — Step 1 stays schema-driven; a filter must never change
  the identified ER pattern, only the data volume/density the selector sees.

## Invariants preserved

- Blind/gold separation: `apply_filters.py` sees only rows; filters are user input and never touch the
  gold file or leak expected patterns/visualisations.
- Std-lib only; no new dependency; CLI mirrors the existing scripts.
- Step-1/2/3 contracts unchanged — the filter is an additive stage; with `filters == []` the pipeline
  behaves exactly as before.
