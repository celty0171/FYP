# VizLM — LLM-powered visualisation, guided by your database's structure

VizLM turns a database selection into an interactive web visualisation. It classifies the
schema pattern of what you pick (a table + columns), recommends a chart that fits that
structure, and renders it — optionally letting an LLM take your plain-language request and
pick the chart. The demo ships with the offline **Mondial** dataset, so it runs with no
setup and no network calls at serve time.

## Requirements

- **Python 3.10+**.
- **PostgreSQL** (the app reads a live database by default).
- Python packages: `pip install -r requirements.txt` (SQLAlchemy + psycopg2 + openai).

## Quick start (live database — default)

```bash
pip install -r requirements.txt

# 1. Create an empty database and load the bundled Mondial dump into it
createdb mondial
python experiments/scripts/load_mondial_postgres.py \
    --url postgresql+psycopg2://postgres@localhost:5432/mondial

# 2. Point the app at it
cp .env.example .env          # then set PG_HOST/PG_PORT/PG_USER/PG_PASSWORD/PG_DATABASE
                              # (or a single DATABASE_URL). VIZER_DATASOURCE=postgres is default.

# 3. Run
python experiments/web_pipeline/server.py --port 8090
```

Then open <http://127.0.0.1:8090>, pick a table and some columns, and a chart is built for
you. (`load_mondial_postgres.py` reads the same `.env` connection settings if you omit
`--url`.) If the database can't be reached at startup the server prints one line explaining
what to fix and exits — it does not silently fall back.

## Offline (JSON) mode — no database

Set `VIZER_DATASOURCE=json` in `.env` (or the environment) to run against the bundled Mondial
JSON files with no PostgreSQL:

```bash
VIZER_DATASOURCE=json python experiments/web_pipeline/server.py --port 8090
```

## Natural language + LLM chart choice (optional)

In `.env`, set `DASHSCOPE_API_KEY` (an OpenAI-compatible Alibaba Cloud Bailian / DashScope
key) to enable plain-language input, and `VIZER_LLM_STEP2=on` to let the LLM rank charts. Both
degrade gracefully to the deterministic path if no key is set.

## How it works

A selection flows through a deterministic three-step pipeline — **Step 1** identifies the ER
schema pattern, **Step 2** recommends a chart and maps columns to its roles, **Step 3**
renders it with D3. Each step is an ahead-of-time authored program, so serving involves **no
model calls** (the optional LLM only assists natural-language parsing and chart ranking).
