# VizLM — LLM-powered visualisation, guided by your database's structure

VizLM turns a database selection into an interactive web visualisation. It classifies the
schema pattern of what you pick (a table + columns), recommends a chart that fits that
structure, and renders it — optionally letting an LLM take your plain-language request and
pick the chart. The demo ships with the offline **Mondial** dataset, so it runs with no
setup and no network calls at serve time.

## Requirements

- **Python 3.10+** (no packages needed to run the bundled demo — the core is standard library).
- Optional packages only for the live-database and natural-language / LLM features
  (see below): `pip install -r requirements.txt`.

## Quick start

```bash
python experiments/web_pipeline/server.py --port 8090
```

Then open <http://127.0.0.1:8090>. By default it serves the bundled Mondial JSON dataset —
pick a table and some columns (or connect your own database in the UI) and a chart is built
for you.

## Optional: live database + natural language + LLM chart choice

```bash
pip install -r requirements.txt      # SQLAlchemy + psycopg2 + openai
cp .env.example .env                  # then edit .env
```

In `.env`:

- Live **PostgreSQL**: set `VIZER_DATASOURCE=postgres` and `DATABASE_URL` (or the `PG_*` parts).
- **Natural-language** input and **LLM chart selection**: set `DASHSCOPE_API_KEY` (an
  OpenAI-compatible Alibaba Cloud Bailian / DashScope key), and set `VIZER_LLM_STEP2=on` to
  let the LLM rank charts. Both degrade gracefully to the deterministic path if no key is set.

## How it works

A selection flows through a deterministic three-step pipeline — **Step 1** identifies the ER
schema pattern, **Step 2** recommends a chart and maps columns to its roles, **Step 3**
renders it with D3. Each step is an ahead-of-time authored program, so serving involves **no
model calls** (the optional LLM only assists natural-language parsing and chart ranking).
