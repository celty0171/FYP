# sql_codegen — Step 0 (data layer): LLM-authored SQL builder

Extends the LLM-as-compiler paradigm to the data-marshalling layer. Instead of fetching a
`SELECT * … LIMIT 5000` sample and doing join/filter/aggregate in Python, the model authors
**one deterministic program** at compile time that emits a single parameterised PostgreSQL
query performing the same work in the database — so aggregation and filter statistics are
**exact over the full table**, and only the needed rows cross the wire.

## Files

- `build_selection_sql_reference.py` — the authoritative program:
  `build_selection_sql(schema, selection) -> (sql_text, params)`. Std-lib only; reuses
  `join.join_tables.find_paths` for FK paths so JOIN construction cannot drift from the offline
  `enrich`. Layers: CTE `j` (base + LEFT-JOINed brought columns) → `WHERE` (row filters +
  `group_having`) → optional `GROUP BY` (resample buckets, measures, `HAVING`) → `ORDER BY` +
  `LIMIT`. Named `:pN` placeholders only; values are bound, never interpolated.
- `compare_sql_vs_python.py` — the reference-vs-generated **oracle**. Sources **both** paths
  from the live PG (so the comparison isolates builder logic from data provenance), runs the
  offline Python path (`join.enrich` → `filter.apply` → `aggregate.prepare`) and the SQL path,
  and asserts an order-insensitive multiset match on the columns that matter.
- Prompt contract: `experiments/prompts/sql_builder_prompt.md`.

## Result

`18/18` cases agree exactly (blind cases 1–9 plus range/in/gt+not_null filters, a forward join,
sum/resample/count_distinct/having aggregates, and a `group_having` filter):

```
18/18 cases agree
```

## Contract, invariants, and known divergences

- **Blind/gold clean:** the builder sees only the schema + selection — never a pattern or gold
  label. Verified by construction (no Step-1/2 import, no pattern field read).
- **Safety:** filter values are bound params (`:pN`), identifiers are validated against the
  schema and quoted. The read-only transaction + `statement_timeout` are enforced by
  `PostgresDataSource` at execution time.
- **Display limit ≠ marshalling:** `limit` is a top-N ceiling ordered measure-desc (an analyst's
  truncation), so the oracle runs **unbounded**; top-N ordering is not part of the equivalence
  contract.
- **One permitted divergence:** a `first`-policy join over a *multiplying* reverse hop is
  collapsed with `DISTINCT ON (base pk)`; the representative row kept may differ from the offline
  `min`-json tiebreak. Forward / 1:1 joins and `explode` joins are exact.
- **Data provenance note:** the bundled JSON fixture (`mondial_data.json`) is a *different*
  Mondial snapshot from the loaded PG (e.g. some `INTEGER`-typed columns rounded; a few lake
  elevations differ by 1), which is why the oracle sources both paths from the live DB rather
  than comparing DB-vs-fixture.

## Run

```
.../envs/fyp/bin/python experiments/results/sql_codegen/compare_sql_vs_python.py
```
