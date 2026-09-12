# filter — Phase 1 same-table row filtering

The deterministic **prepare** stage of the pipeline. It takes the chosen relation's rows and a filter
spec and returns the matching subset, *before* Step 2. The Step-2 selector then measures density / N on
the subset, and the Step-3 renderer draws it — so recommendations and charts both reflect the subset
the user actually asked for. See `PLAN.md` for the full design.

**Renderers are untouched.** Each renderer reads rows via `_rows_for(mapping, data)` →
`data["tables"][mapping["table"]]`, so the server just builds a filtered view
`{"tables": {table: apply(rows, filters)}}` and passes it where it used to pass the global data.

## Filter spec

```json
{ "table": "country_population",
  "filters": [
    { "column": "year",      "op": "range", "min": 1990, "max": 2020 },
    { "column": "continent", "op": "in",    "values": ["Europe", "Asia"] }
  ] }
```

Operators (conjunctive — a row must satisfy every filter):

| op         | applies to        | semantics                                       |
|------------|-------------------|-------------------------------------------------|
| `range`    | scalar / temporal | `min ≤ value ≤ max` (either bound optional)      |
| `in`       | discrete          | value is in `values`                             |
| `eq`       | any               | sugar for `in` with one `value`                  |
| `not_null` | any               | drop rows whose column is null/absent            |

An empty `filters` list is the identity (no-op). A filter naming a column absent from a row drops that
row; an unknown `op` is ignored (forward-compatible). `range`/`eq` coerce via `float`, so a spec
`"2000"` matches an integer `2000`.

## `apply_filters.py`

- `apply(rows, filters) -> list[dict]` — the conjunctive filter above; pure, order-preserving.
- `column_stats(rows, columns=None) -> dict` — per-column metadata for the UI to build controls:
  scalar/temporal → `{dim, min, max, count}`; discrete → `{dim, distinct, values}` up to
  `MAX_DISTINCT = 60`, else `{dim, distinct, high_cardinality: true}`.

Standard library only; no schema/gold knowledge (operates purely on rows, preserving the blind/gold
separation invariant).

### CLI

```bash
python schemavislm/filter/apply_filters.py \
    --data schemavislm/mondial_database/mondial_data.json \
    --spec filter_spec.json \
    --out  filtered_rows.json \
    [--stats]        # also print column_stats for the unfiltered table to stderr
```

## Web integration (`web_pipeline/`)

- `GET/POST /api/column_stats` — `{table[, columns]}` → control metadata (from the *unfiltered* table,
  so ranges stay stable).
- `/api/run` and `/api/render` accept a `filters` array; `run_pipeline` applies it before Step 2 and
  renders the subset, echoing `filters` back so pill clicks resend the same subset. An empty result
  shows "no rows match the current filter" instead of erroring.
