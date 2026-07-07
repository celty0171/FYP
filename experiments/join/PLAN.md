# Phase 2 — Cross-table join (foreign-column enrichment): implementation plan

## Goal

Phase 1 lets a user subset **one table's** rows. But real questions reach across tables: "show
`country_population` **by continent**" (continent lives in `encompasses`, not in `country_population`);
"colour cities by their country's GDP" (GDP lives in `economy`). Phase 2 adds a **join / enrichment**
stage that attaches a column from a *related* table onto the base relation's rows by following the
schema's foreign-key graph. Once attached, the foreign column is just another column, so **everything
downstream is unchanged** — the Phase-1 filter can filter by it, the Step-2 selector sees it as an
extra attribute, and every renderer draws it.

## Design principle: enrich to a denormalised same-table, before filter

The join is another deterministic *prepare* stage, sitting **before** Phase-1 filtering:

```
selection = { table, columns, joins, filters }
      │
      ▼
[ join ]   base rows  +  foreign columns via FK path   →  enriched rows (fatter dicts)
      │
      ▼
[ filter ] Phase-1 same-table filter on the enriched rows          (unchanged)
      │
      ├─►  Step 2 selector   measures on the enriched+filtered rows (unchanged)
      └─►  Step 3 renderer   render(mapping, rows)                  (unchanged)
```

The output of the join is still **one relation's rows** — a list of dicts, just with extra keys — so
the filter, selector and every renderer keep working with no change. Join runs *before* filter so a
user can both attach `continent` **and** filter to `Europe` in the same request.

Why before Step 2 and Step 1 is unaffected: Step 1 classifies the ER pattern from the **schema** of the
base table's selected keys/FKs; an enriched foreign column is neither a PK nor an FK of the base table,
so it reads as an ordinary attribute (e.g. a discrete `continent` for colouring/filtering). **A join
must never change the identified pattern** — it only adds an attribute the selector and renderers can
use. This is the Phase-2 counterpart of the Phase-1 "filters never re-classify" invariant.

## The FK graph and path-finding

Build a graph from `schema.tables[*].foreign_keys` with two kinds of edge:

- **forward** (`child.fk_cols → parent.pk_cols`): the base row holds a foreign key pointing at exactly
  **one** parent row. Many-to-one — a safe *lookup*, never multiplies rows.
- **reverse** (`parent.pk_cols → child.fk_cols`): stepping from a parent into a child/bridge table
  (e.g. `country → encompasses`). Can be one-to-many. **A reverse hop multiplies only when the child's
  primary key has columns *beyond* the FK** (so one parent maps to many child rows): `encompasses`
  (PK `[country, continent]` ⊋ FK `[country]`) multiplies; `economy` (PK `[country]` == FK `[country]`)
  is **1:1 and does not multiply**. Verified on the real schema — the multiplies flag must be computed
  from `child.PK ⊋ fk.columns`, not from the hop direction alone.

To bring a column `T.c` onto base table `B`, BFS the graph from `B` for the shortest path to `T`; each
hop carries its join-key correspondence (the FK-column ↔ PK-column pairs, composite keys included, e.g.
`city.(province,country) → province.(name,country)`). Prefer all-forward paths (pure lookups) when one
exists; fall back to paths that include a reverse hop, flagging them as multiplying.

## Multiplicity policy (the crux)

A path attaches one value per base row whenever every hop is either forward or a **1:1 reverse** (child
PK == FK) — clean, cardinality preserved. Only a **multiplying reverse hop** (child PK ⊋ FK, e.g.
`encompasses`, where a country spans several continents) can match several child rows, so the engine
needs a policy for those:

| policy      | effect                                                                 | good for |
|-------------|------------------------------------------------------------------------|----------|
| `first`     | keep one match (deterministic: sorted by join value); **row count unchanged** | safe default; bar/line where inflated counts would mislead |
| `explode`   | emit one enriched row per match; **row count grows**                    | filtering ("show only Europe" keeps a multi-continent country under Europe) |
| `aggregate` | collapse matches with an aggregate (count/sum/first)                    | deferred to the aggregation phase |

Phase-2 default is **`first`** (honest cardinality, deterministic); `explode` is opt-in and clearly
labelled in the UI as "may duplicate rows", because it changes what a chart's counts mean. `aggregate`
is out of scope until same-table aggregation lands (see *Dependencies*).

## Join spec (the contract)

Carried alongside `filters` on `/api/run` and `/api/render`. Two forms — an explicit path or an auto
form the engine resolves:

```json
{
  "table": "country_population",
  "joins": [
    { "bring": "encompasses.continent", "as": "continent", "policy": "first" }
  ],
  "filters": [ { "column": "continent", "op": "in", "values": ["Europe"] } ]
}
```

- `bring` — `"<table>.<column>"` to attach (the engine finds the path), or a fully explicit
  `{ "path": [ {from, to, on:[[fkcol,pkcol],...]}, ... ], "column": "..." }`.
- `as` — output column name on the enriched rows (defaults to the source column; namespaced
  `table__column` on collision with an existing base column).
- `policy` — `first` (default) | `explode`; only consulted when the path has a reverse hop.

An empty/absent `joins` list is the identity — the pipeline behaves exactly as Phase-1.

## Deliverables

### 1. `experiments/join/join_tables.py` (new, std-lib only)

The deterministic enrichment program (the LLM-as-compiler artefact for this stage). Public functions:

- `fk_graph(schema) -> adjacency` — forward + reverse edges with join-key correspondences.
- `find_paths(schema, base_table, target_table) -> list[path]` — BFS shortest path(s), each hop
  carrying its `on` key pairs and a `reverse: bool` flag.
- `reachable_columns(schema, base_table, max_hops=2) -> list[{table, column, path, multiplies}]` — every
  foreign column the UI can offer for a base table (bounded hop count to keep the menu sane).
- `enrich(base_rows, schema, tables_data, joins) -> list[dict]` — resolve each join's path, index the
  intermediate/target tables by their join keys, and attach `as` columns to each base row per `policy`.
  Pure; never mutates input; deterministic ordering.
- CLI `--schema --data --spec --out` mirroring `apply_filters.py`, so a join can be applied and
  inspected offline.

No gold knowledge; operates on schema + rows only (preserves blind/gold separation).

### 2. `experiments/web_pipeline/server.py` (edit)

- Load the module: `JOIN = _load(EXP / "join" / "join_tables.py", "prepare_join")`.
- In `run_pipeline` (and the `/api/render` data path) apply the join **before** the filter:
  `rows = JOIN.enrich(DATA.tables[table], SCHEMA, DATA["tables"], joins)` → then Phase-1
  `FILTER.apply(rows, filters)` → wrap as `{"tables": {table: rows}}`.
- `/api/run` and `/api/render` bodies gain a `joins` array (echoed back like `filters`).
- New `GET/POST /api/join_options` → `JOIN.reachable_columns(SCHEMA, table)` so the UI can list the
  foreign columns available for the chosen base table, each with its `multiplies` flag.
- The empty-result guard and `column_stats` (now computed on the *enriched* rows so a joined column
  gets a control) are reused.

### 3. `experiments/web_pipeline/index.html` (edit)

- A new **"Related columns (join)"** control above the Filters panel: a dropdown/checklist populated
  from `/api/join_options`; choosing one adds it to the `joins` spec and, after the next stats fetch,
  the column appears in the Filters panel automatically (so "attach continent, then filter Europe" is
  two clicks). Columns whose path multiplies show a small "may duplicate rows" hint and a
  `first`/`explode` toggle (default `first`).
- Thread `joins` through `/api/run` and every pill `/api/render`, alongside `filters`.

### 4. `experiments/join/README.md` (new)

Spec format, the forward/reverse/multiplicity model, the CLI example, and the "enrich to a
denormalised same-table, before filter; renderers untouched" architecture line.

## Worked examples (acceptance)

| Base selection | Join | Then | Expected |
|----------------|------|------|----------|
| `country_population` (country, year, population) | `bring encompasses.continent` (`first`) | filter `continent in {Europe}` | rows keep one continent each; only European countries' population series remain; pattern still `weak_entity` (verified: 2278 rows preserved, 543 after Europe filter) |
| `country_population` (country, year, population) | `bring economy.gdp` (2 hops, 1:1 reverse) | — | each row gains its country's `gdp`; **no** row multiplication (verified: 2278 → 2278) |
| `city` (name, country, population) | `bring province.area` (composite FK `[province,country]`) | — | composite-key join resolves correctly (verified: 3423 rows, area attached) |
| `country_population` | `bring encompasses.continent` (`explode`) | filter `Europe` | a country spanning Europe+Asia appears under Europe; row count exceeds the base (verified: 2278 → 2329) |
| any | no joins | — | identical to Phase-1 (regression: identity) |

## Verification

1. **Path-finding:** `find_paths` returns the expected hops for `country_population→encompasses`
   (one reverse hop, `multiplies=True`) and `city→economy` (all forward, `multiplies=False`).
2. **Enrichment cardinality:** `enrich` with `first` preserves `len(base_rows)`; with `explode` grows
   it by the fan-out; a pure-forward join always preserves it. Composite join keys
   (`city→province`) resolve correctly.
3. **Downstream unchanged:** after enrich, `apply_filters.apply` filters the joined column;
   `STEP2.recommend` sees it as a discrete/scalar attribute; Step 1 pattern is **unchanged** vs the
   un-joined base selection.
4. **End-to-end (server):** `/api/join_options` lists reachable columns; `/api/run` with `joins`+
   `filters` renders the enriched+filtered subset; `/api/render` keeps `joins` on a pill click;
   identity (`joins=[]`) is byte-identical to Phase-1.

## Dependencies & sequencing

- **Same-table aggregation is still open** (Phase-1 PLAN listed it out of scope and it was not built).
  Join's `aggregate` multiplicity policy — and honest "sum population by continent" — depend on it.
  Recommended order: land this forward/`first`/`explode` join first (it already unblocks the motivating
  "by continent" filtering case), then do same-table aggregation, then wire the `aggregate` policy.

## Out of scope (later)

- `aggregate` join policy and group-by/resample (need the aggregation stage first).
- Paths longer than a small hop bound, and many-to-many *chains* through several bridges.
- Attaching more than a couple of foreign columns at once (kept minimal for a legible UI).

## Invariants preserved

- Blind/gold separation: `join_tables.py` reads schema + rows only; never the gold file.
- Std-lib only; CLI mirrors the existing scripts; a new sibling folder to `filter/`.
- Step-1/2/3 contracts unchanged — join is an additive stage; with `joins == []` the pipeline behaves
  exactly as Phase-1. A join never re-classifies the ER pattern.
