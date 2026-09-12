# join — Phase 2 cross-table join (foreign-column enrichment)

The deterministic **enrich** prepare stage. It attaches a column from a related table onto the base
relation's rows by following the schema's foreign-key graph, so everything downstream — the Phase-1
filter, aggregation, and Step 1/2/3 — sees it as an ordinary extra attribute. Renderers are untouched.
See `PLAN.md` for the full design.

Pipeline order: `join (enrich) → filter (Phase 1) → aggregate (Phase 1b) → Step 1/2/3`.

## FK graph & multiplicity

Two edge kinds are derived from the schema:

- **forward** `child.fk_cols → parent.pk_cols` — the base row holds an FK to exactly one parent.
  Always 1:1, never multiplies.
- **reverse** `parent.pk_cols → child.fk_cols` — step into a child/bridge table. **Multiplies only when
  the child's primary key has columns beyond the FK** (one parent → many children):
  `encompasses` (PK `[country, continent]` ⊋ FK `[country]`) multiplies; `economy`
  (PK `[country]` == FK `[country]`) is 1:1 and does not.

The `multiplies` flag is computed from `child.PK ⊋ fk.columns`, **not** from hop direction — a reverse
hop into a 1:1 child does not grow the row set.

## Join spec

```json
{ "table": "country_population",
  "joins": [ { "bring": "encompasses.continent", "as": "continent", "policy": "first" } ] }
```

- `bring` — `"<table>.<column>"`; the engine finds the shortest FK path (BFS). An explicit
  `{ "path": [...], "column": "..." }` form is also accepted.
- `as` — output column name; namespaced `table__column` on collision with a base column.
- `policy` — `first` (default; keep one deterministic match, cardinality preserved) or `explode` (one
  row per match; only matters on a multiplying hop).
- An empty/absent `joins` list is the identity.

## `join_tables.py`

- `fk_graph(schema)` — forward + reverse edges with join-key correspondences.
- `find_paths(schema, base, target)` — shortest FK path(s), each hop flagged `reverse` / `multiplies`.
- `reachable_columns(schema, base, max_hops=2)` — foreign columns offerable for a base table, each with
  its path and a `multiplies` flag.
- `enrich(schema, tables_data, base_table, base_rows, joins)` — attach each join's column via its path.
  Uses a **frontier-row** traversal (keeps a reference to the matched row at each hop and reads the
  brought column from it), so a joined column never collides with a same-named base column. Pure;
  left-join semantics (unmatched → `None`); deterministic.

Standard library only; schema + rows only (preserves blind/gold separation).

### CLI

```bash
python schemavislm/join/join_tables.py --schema schema.json --data data.json \
    --spec join_spec.json --out rows.json          # enrich
python schemavislm/join/join_tables.py --schema schema.json --data data.json \
    --spec '{"table":"country_population"}' --out reach.json --reachable   # list reachable columns
```

## Web integration (`web_pipeline/`)

- `GET/POST /api/join_options` → `{table}` → reachable foreign columns (`bring`, `hops`, `multiplies`).
- `/api/run` and `/api/render` accept a `joins` array (echoed back); `run_pipeline` enriches **before**
  filter/aggregate. `/api/column_stats` accepts `joins` too, so a joined column gets a filter control.
- Chaining works end-to-end: "join `encompasses.continent` → aggregate `sum(population)` by continent"
  yields a derived `basic_entity` → bar chart, entirely through the existing Step 1/2/3 programs.
