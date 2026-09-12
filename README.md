# SchemaVisLM — LLM-powered visualisation, guided by your database's structure

SchemaVisLM turns a database selection into an interactive web visualisation. It classifies the
schema pattern of what you pick (a table + columns), recommends a chart that fits that
structure, and renders it — optionally letting an LLM turn your plain-language request into a
selection and pick the chart. It is **database-agnostic**: the bundled **Mondial** dataset lets
you try it with no setup, but you can point it at your own PostgreSQL just as easily.

**🌐 Live demo:** <https://schemavislm.onrender.com>

> The hosted instance is provided mainly for **presentation**. It may be temporarily unusable —
> the free tier **sleeps after ~15 min idle** (the first hit cold-starts slowly), and the LLM
> features can stop if the `qwen3.7-flash` API quota is exhausted (they then degrade to the
> deterministic path). For a reliable experience, **run the service locally** (see below).

## Requirements

- **Python 3.10+**.
- **PostgreSQL** (the app reads a live database by default).
- Python packages: `pip install -r requirements.txt` (SQLAlchemy + psycopg2 + openai).

## Quick start (live database — default)

```bash
pip install -r requirements.txt

# 1. Create an empty database and load the bundled Mondial dump into it
createdb mondial
python schemavislm/scripts/load_mondial_postgres.py \
    --url postgresql+psycopg2://postgres@localhost:5432/mondial

# 2. Point the app at it
cp .env.example .env          # then set PG_HOST/PG_PORT/PG_USER/PG_PASSWORD/PG_DATABASE
                              # (or a single DATABASE_URL). SCHEMAVISLM_DATASOURCE=postgres is default.

# 3. Run
python schemavislm/web_pipeline/server.py --port 8090
```

Then open <http://127.0.0.1:8090>, pick a table and some columns, and a chart is built for
you. (`load_mondial_postgres.py` reads the same `.env` connection settings if you omit
`--url`.) If the database can't be reached at startup the server prints one line explaining
what to fix and exits — it does not silently fall back.

**One-command local run.** If PostgreSQL is installed locally, `./run_local.sh` brings up a
co-located database, loads Mondial and starts the server in one step:

```bash
./run_local.sh                 # DB on 5432, web UI on http://127.0.0.1:8090
```

See [`schemavislm/web_pipeline/README.md`](schemavislm/web_pipeline/README.md) for the full
options and troubleshooting; stop the database later with `./start_pg.sh stop`.

## Offline (JSON) mode — no database

Set `SCHEMAVISLM_DATASOURCE=json` in `.env` (or the environment) to run against the bundled Mondial
JSON files with no PostgreSQL:

```bash
SCHEMAVISLM_DATASOURCE=json python schemavislm/web_pipeline/server.py --port 8090
```

## Use your own database

SchemaVisLM isn't tied to Mondial. Point it at **any PostgreSQL** — either set `DATABASE_URL` (or the
`PG_*` parts) in `.env`, or use the **connect form** in the web UI. Everything downstream is generic:
the pattern classification, geographical-column detection, alternative-key discovery and the SQL
pushdown all work from your schema's primary-key / foreign-key structure, so the same
selection → pattern → chart pipeline applies to your own tables.

## Natural language + LLM chart choice (optional)

In `.env`, set `DASHSCOPE_API_KEY` (an OpenAI-compatible Alibaba Cloud Bailian / DashScope
key) to enable plain-language input, and `SCHEMAVISLM_LLM_STEP2=on` to let the LLM rank charts. Both
degrade gracefully to the deterministic path if no key is set.

## Deploy (Render)

The repo ships a `render.yaml` Blueprint and a `Dockerfile` for a shareable hosted demo:

1. Render → **New → Blueprint** → connect this repo → pick `main`. It provisions a managed
   PostgreSQL (`schemavislm-db`) and the web service, wiring the `PG_*` variables automatically.
2. *(Optional)* set `DASHSCOPE_API_KEY` on the web service to enable the LLM features.
3. **One-time**, load Mondial into the managed database using its **external** connection URL, then
   restart the web service (it reads the schema at startup):
   ```bash
   python schemavislm/scripts/load_mondial_postgres.py \
       --url "postgresql+psycopg2://<user>:<pass>@<external-host>:5432/<db>?sslmode=require"
   ```

## Repository layout

```
schemavislm/
  web_pipeline/     std-lib web app: server.py, index.html, vendored D3
  results/          the ahead-of-time authored programs the server runs:
                      step1_codegen/   ER-pattern classifier
                      step2_codegen/   chart recommender + column mapping
                      sql_codegen/     SQL builder
                      viz_codegen_*/   one D3 renderer per chart
  config.py, datasource/, geodetect/, chartselect/, nlquery/   production layer
  filter/  aggregate/  join/    optional deterministic data-prep stages
  mondial_database/  bundled Mondial dump (SQL + JSON) + world basemap
  scripts/          schema extraction + Mondial → PostgreSQL loader
  prompts/          the prompts used to author the programs above
  evaluation/       external NL → visualisation test set
Dockerfile, render.yaml     container image + Render Blueprint for deployment
run_local.sh, start_pg.sh   one-command local PostgreSQL + server
```

## How it works

A selection flows through a deterministic three-step pipeline — **Step 1** identifies the ER
schema pattern, **Step 2** recommends a chart and maps columns to its roles, **Step 3**
renders it with D3. Each step is an ahead-of-time authored program, so serving involves **no
model calls** (the optional LLM only assists natural-language parsing and chart ranking).
