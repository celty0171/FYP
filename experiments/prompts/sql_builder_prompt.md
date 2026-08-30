You are an expert in relational query generation and the VizER schema-pattern pipeline (McBrien & Poulovassilis). Your task is **not** to answer one query by hand. Your task is to **write one deterministic Python program**, once, that turns a user's data selection into a single parameterised PostgreSQL query — the "compile-time" artefact of the LLM-as-compiler approach, extended to the data layer.

This is **Step 0** of the runtime: it sits in front of Step 1 (pattern) → Step 2 (chart) → Step 3 (render). The offline experiment path performs the same work in Python — `join.enrich` → `filter.apply` → `aggregate.prepare` — over bundled JSON rows. Pushing it into the database instead makes aggregation and filter statistics **exact over the whole table** (not a capped sample) and cuts data transfer. Your program is authored against the schema and the selection only; it runs reproducibly at run time with the data read inside the database.

# What you write

A standard-library module exposing:

    build_selection_sql(schema, selection) -> (sql_text, params)

- `schema` is the clean schema dict: `{"tables": {t: {"columns":[{"name","type","nullable"}], "primary_key":[...], "foreign_keys":[{"columns","references_table","references_columns"}], "unique_constraints":[...]}}}`.
- `selection = {"table", "columns", "joins", "filters", "aggregate", "limit"}` (all but `table` optional).
- `sql_text` uses named `:p0, :p1, …` placeholders **only**; `params` is the matching `{name: value}` dict. The caller binds them — **never** interpolate a filter value into the SQL string. This is the whole injection defence.

# Hard invariants

- **Blind/gold separation.** You receive the schema and the selection — never a pattern label, an expected visualisation, or any gold answer. Do not read, infer, or emit them. Reason only from primary-key / foreign-key structure and SQL types, exactly as the offline stages do.
- **Standard library only.** No third-party imports. (You may reuse the project's own std-lib FK-graph helper, `join.join_tables.find_paths`, so JOIN construction cannot drift from the offline `enrich`.)
- **Quote every identifier** you validate against the schema (`"col"`, internal quotes doubled). Resolve each selection column to its real, case-correct schema name before quoting; skip a column that is not in the schema rather than trusting the caller's spelling.
- **Agreement with the offline stages is the contract.** For any selection, the rows your query returns must equal the rows the Python path returns over the same data (order-insensitive multiset). `results/sql_codegen/compare_sql_vs_python.py` is the oracle.

# The query, layered exactly as the offline stages run

Emit a query with these layers (a CTE named `j`, then a select over it):

1. **`j` — join.** `FROM "<base>" AS b`, then for each `join` (`{"bring": "table.col", "as": "alias", "policy": "first"|"explode"}`) find the shortest FK path with `find_paths(schema, base, target)` and translate each hop into a `LEFT JOIN` with a unique alias, `ON` the hop's column pairs. Project `b.*` plus each brought column aliased (mirror `enrich`'s aliasing: `as` if given, else the column name; on a name collision, `target__col`). A forward (child→parent) or 1:1 reverse hop is exact. An `explode` policy on a **multiplying** reverse hop multiplies rows (match the offline `explode`); a `first` policy on a multiplying hop must collapse to one row per base identity — use `DISTINCT ON (b.<pk…>)` (document that the representative row may differ from the offline json-tiebreak; this is the one permitted narrow divergence).

2. **filter.** Apply `filters` as a `WHERE` over `j` (before any aggregation — the offline order is filter-then-aggregate). Support every operator the offline filter does, each with **bound params**: `range` (`>= :min AND <= :max`, either bound optional, plus `IS NOT NULL`), `in` (`IN (:…)`), `eq` (`= :v`), `not_null` (`IS NOT NULL`), and `gt/ge/lt/le`. A `group_having` filter keeps member rows without collapsing them — render it as `(<keys>) IN (SELECT <keys> FROM j GROUP BY <keys> HAVING <agg cond>)`.

3. **aggregate (optional).** When `aggregate` has `group_by`/`measures`/`resample`: compute each `resample` bucket as `(FLOOR("col"::numeric / :b) * :b)::bigint` and expose it under its `as` alias; `GROUP BY` the dimensions; emit each measure as `SUM/AVG/MIN/MAX(col)`, `COUNT(*)`, or `COUNT(DISTINCT col)` under its alias (`as`, else `count` for count, else `fn_col`); apply post-aggregate `having` as a real SQL `HAVING` referencing the aggregate **expression** (not the output alias). Exclude nulls for mandatory attributes as the offline reducers do.

4. **order + limit.** `limit` is a **display top-N ceiling**, applied last. Order by the first measure descending when aggregating (the useful cut — like an analyst truncating to the largest groups), else by the key columns; then `LIMIT :n`. (The equivalence oracle runs unbounded, because top-N ordering is a display choice, not part of the marshalling contract.)

# Reference

`results/sql_codegen/build_selection_sql_reference.py` is the authoritative program; `PostgresDataSource.get_selection` loads it. Keep any sibling (e.g. a GPT-authored `gpt_build_selection_sql.py`) to the same contract and oracle.
