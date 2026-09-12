# web_pipeline — the live SchemaVisLM front end

A web UI that runs the full current pipeline end to end:

**connect a live database → pick data (by clicking columns *or* typing a request in plain
English) → push one SQL query to fetch it → identify the ER pattern → recommend a chart +
field mapping → render an interactive D3 chart.**

The three pipeline stages (Step 1 pattern, Step 2 chart + mapping, Step 3 renderers) and the
data-layer SQL builder are all **LLM-authored deterministic programs, generated once at
"compile time"** and run reproducibly here with **no model calls needed at serve time**. On
top of that sit three **optional, on-by-default LLM levers** (natural-language input, Step-2
ranking, geographical-column detection) that each need an API key and degrade gracefully to
the deterministic path without one.

> If you just want the shortest path: install deps, `cp .env.example .env` (add a
> `DASHSCOPE_API_KEY` for the natural-language box), then `conda activate fyp && ./run_local.sh`
> from the repo root, and open the printed URL.

---

## 1. Prerequisites

The live-DB + NL layer needs three third-party packages (`SQLAlchemy`, `psycopg2`, `openai`);
the experiment core stays std-lib. On this HPC they are already installed in the **`fyp` conda
environment** — use it for everything below:

```bash
conda activate fyp
# (first time on a fresh machine instead: pip install -r schemavislm/requirements.txt)
```

You also need a **PostgreSQL** with Mondial loaded. Two options — a throwaway co-located one
that `run_local.sh` sets up for you (§3), or your own existing database (§5).

---

## 2. Configure `.env` (repo root)

Copy the template and edit the repo-root `.env` (it is gitignored):

```bash
cp .env.example .env
```

What matters for the **latest full experience**:

| key | set it to | effect if unset / off |
|-----|-----------|------------------------|
| `SCHEMAVISLM_DATASOURCE` | `postgres` (default) | `json` uses the bundled offline Mondial files (no DB needed, but no live SQL) |
| `PG_HOST` / `PG_PORT` / `PG_USER` / `PG_PASSWORD` / `PG_DATABASE` | your DB, **or** leave for `run_local.sh` to fill | — |
| `DASHSCOPE_API_KEY` | **your Bailian/DashScope key** | **no key ⇒ the natural-language box, LLM chart ranking and LLM geo-detection all switch off** and the pipeline runs fully deterministic (still works, just without those LLM features) |
| `SCHEMAVISLM_PUSHDOWN` | `on` (default) | `off` forces the fetch-then-Python path instead of one pushed-down SQL query (aggregation/stats then reflect a `SCHEMAVISLM_ROW_CAP` sample, not the whole table) |
| `SCHEMAVISLM_STATEMENT_TIMEOUT_MS` | `15000` (default) | per-query ceiling for pushed-down SQL |
| `SCHEMAVISLM_ROW_CAP` | `5000` (default) | hard ceiling on rows fetched per table; the UI's display *top-N* is `min()`'d with this |
| `SCHEMAVISLM_LLM_STEP2` / `SCHEMAVISLM_LLM_GEO` | `on` (default) | off keeps Step 2 / geo detection deterministic |

**To experience every feature**, set `SCHEMAVISLM_DATASOURCE=postgres`, point `PG_*` at a Mondial DB,
and add a real `DASHSCOPE_API_KEY`. Everything else can stay at its default.

> `run_local.sh` injects `SCHEMAVISLM_DATASOURCE=postgres` and the `PG_*` for its co-located DB via
> the environment (these override `.env`), but still reads the rest of `.env` — so your
> `DASHSCOPE_API_KEY` and the `SCHEMAVISLM_*` flags there are picked up.

---

## 3. Quickest path — one command (co-located throwaway DB)

From the **repo root**, with the `fyp` env active:

```bash
conda activate fyp
./run_local.sh                 # DB on 5432, web UI on http://127.0.0.1:8090
```

This runs `start_pg.sh` (idempotent: `initdb` on first run, start PostgreSQL, create the DB,
**load Mondial** if empty) and then launches the server against it. Useful overrides:

```bash
PORT=9000 ./run_local.sh                 # custom web port
PGPORT=5433 DBNAME=mydb ./run_local.sh   # custom DB port / name (kept in sync with start_pg.sh)
HOST=0.0.0.0 ./run_local.sh              # bind all interfaces (e.g. inside a container)
```

On the HPC, tunnel the web port from your laptop, then open the URL locally:

```bash
ssh -L 8090:localhost:8090 <you@hpc>     # then browse http://localhost:8090
```

Stop the database later with `./start_pg.sh stop`.

---

## 4. Using the UI (the full link)

1. **Connect** — the connect form is prefilled from `.env` (never the password). Click Connect;
   the status badge turns green and the schema loads. Each column is badged with its key/FK role
   and semantic type(s) (numeric / temporal / lexical / geographical).
2. **Pick data — two ways, both end at the same place:**
   - **Manually**: tick columns; optionally add filters, a foreign-column join, or an aggregate
     (group-by + measure, with resample buckets / having).
   - **Natural language**: type a request (e.g. *“total population per continent”*). The LLM
     parses it into the *same* selection JSON and shows it for you to confirm/edit before running.
3. **Run** — the server fetches the data with **one read-only, parameterised SQL query** (join +
   filter + aggregate pushed down; exact over the whole table), classifies the **ER pattern**,
   recommends **charts + a field mapping** (the LLM ranks the deterministic candidates and
   highlights one with a rationale when a key is set), and renders the chosen chart.
4. **Explore** —
   - click any recommended-chart pill to re-render it;
   - use the **role-column switchers** to flip which column fills a chart role (e.g. label by
     `name` instead of `code`);
   - use **show top N rows** to truncate what's drawn (applied *after* grouping — the analysis
     still sees the whole relation); the **“showing N / M rows”** badge reports the cut;
   - zoom / fullscreen / open-in-tab / download the standalone chart HTML.

---

## 5. Alternative — point at your own database

Skip `run_local.sh`; just set `.env` `PG_*` (or `DATABASE_URL`) to your DB and start the server
directly. The server takes **`--port`** (not a `$PORT` env var):

```bash
conda activate fyp
python schemavislm/web_pipeline/server.py --host 127.0.0.1 --port 8090
```

You can also switch the live connection at runtime from the web connect form (host/port/user/
password/database) — it rebinds the active data source and re-detects geographical columns for
the new schema. The system is database-agnostic: any connected PostgreSQL works, not only Mondial.

To load Mondial into an existing PostgreSQL yourself:

```bash
python schemavislm/scripts/load_mondial_postgres.py \
  --url postgresql+psycopg2://<user>@localhost:5432/<db>
```

---

## 6. API (what the UI calls)

- `GET  /api/datasource` → connection status + form defaults.
- `POST /api/connect` `{host,port,user,password,database}` → switch to a live DB.
- `GET  /api/schema` → `{ tables:{<t>:[cols]}, meta:{<t>:{columns:[{name,type,dim,datatypes,pk,fk}], primary_key}} }`.
- `GET/POST /api/column_stats` `{table,joins}` → per-column filter stats (exact `MIN/MAX/COUNT DISTINCT` pushed into SQL on a live DB).
- `GET  /api/join_options?table=` → foreign columns reachable by FK path.
- `POST /api/nl` `{text}` → `{ok, selection}` — the parsed selection to confirm (never a pattern/chart label).
- `POST /api/run` `{table, columns, filters, aggregate, joins, intent, limit}` →
  `{ step1:{pattern,reason,derived_table?}, step2:{recommended_charts,candidates,selected,llm?}, step3:{chart,available,html}, rows_shown, rows_total }`.
- `POST /api/render` `{chart, mapping, table, filters, aggregate, joins, limit}` → `{chart, available, html, rows_shown, rows_total}` — re-render on a swap / top-N change.

`step3.html` is a complete standalone document (D3 vendored inline) shown in a sandboxed iframe,
or the literal `working in process` for any chart name without a renderer.

---

## 7. Verifying the latest data layer

The SQL builder is checked against the offline Python path by a reference-vs-generated oracle
(both sourced from the live DB, so it isolates builder logic):

```bash
python schemavislm/results/sql_codegen/compare_sql_vs_python.py   # expect: 18/18 cases agree
```

`SCHEMAVISLM_PUSHDOWN=off` makes `/api/run` produce identical charts via the Python fallback, and
`SCHEMAVISLM_DATASOURCE=json` runs the whole UI offline against the bundled fixture — handy for a
quick look without a database.

---

## 8. Troubleshooting

- **“could not connect” / SQLAlchemy import error** — you're not in the `fyp` env (`conda activate fyp`).
- **Blank page after connecting** — check the DB actually has Mondial loaded (`start_pg.sh` does this; otherwise §5).
- **Noisy GSSAPI/Kerberos errors on HPC** — the scripts set `PGGSSENCMODE=disable`; if starting the server by hand, prefix it with `PGGSSENCMODE=disable`.
- **Natural-language box does nothing** — no `DASHSCOPE_API_KEY` in `.env` (it degrades off by design). Manual selection still works.
- **Port already in use** — pass a different `--port` (or `PORT=… ./run_local.sh`).
