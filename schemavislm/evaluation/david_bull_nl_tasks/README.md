# NL → visualisation test set (David Bull functional tasks)

An **external, unseen** test set for the natural-language → visualisation pipeline, adapted from the
13 functional-test tasks set by Imperial staff for David Bull's MSc project.
Because the tasks were written by third parties (not derived from our schema), they probe
**generalisation** rather than in-distribution behaviour. David solved them with a deterministic tool
over **hand-written SQL**; here the same wording is typed into our **web NL box** and we measure how
far the LLM NL parser + Step 1/2/3 pipeline gets on its own. Gold answers are in `gold.json`.

Each task is graded on four independent layers: **Sel** (base table + columns), **Pat** (ER pattern),
**Chart** (highlighted chart), and **F/J/A** (filter / join / aggregate — the hardest layer).

# Files

- `gold.json` — gold selections / patterns / charts for the 13 tasks.
- `result_pg_full.json` — the result run (live Postgres); `run_eval.py` produced it.
- `picks.json` — the LLM "best chart" pick per task; `run_picks.py` produced it.
- `run_eval.py` — end-to-end evaluator (`--mode`, `--datasource`, `--samples` / `--temperature`,
  `--from` resume). Needs a live Mondial Postgres; `--mode full` also needs `DASHSCOPE_API_KEY`.
- `run_picks.py` — rebuilds Step-2 candidates on the live data and records the deployed LLM selector's
  pick (aborts rather than recording a deterministic fallback).
