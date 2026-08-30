#!/usr/bin/env python3
"""Local, render-free evaluator for the David-Bull NL->visualisation test set.

It runs the *same* pipeline modules the web server uses (Step-1 pattern classifier + Step-2 chart
recommender) against the offline Mondial JSON data source — no web server, no browser, no Step-3
rendering. Two modes, auto-selected:

* **full**  (needs the ``openai`` package + a DASHSCOPE key): each task's natural-language wording
  is parsed by ``nlquery.nl_to_selection.parse`` into a {table, columns, filters, joins, aggregate}
  selection, exactly as the web NL box does; then Step-1/Step-2 run on that selection. This measures
  the real NL understanding.
* **deterministic** (no key / no ``openai``): the NL layer is skipped and the pipeline is fed the
  *gold* table+columns, so only the Step-1 pattern and Step-2 chart layers are scored. Clearly
  labelled ``NL: skipped`` per task.

Scoring is by the gold in ``gold.json`` and is deliberately lenient/transparent: it prints what each
layer produced so you can eyeball borderline cases. Usage::

    python experiments/evaluation/david_bull_nl_tasks/run_eval.py            # auto mode
    python experiments/evaluation/david_bull_nl_tasks/run_eval.py --mode deterministic
    python experiments/evaluation/david_bull_nl_tasks/run_eval.py --out results.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]                       # experiments/
sys.path.insert(0, str(EXP))
sys.path.insert(0, str(EXP / "results" / "prompt_v9_codegen"))

TAXONOMY = {
    "basic_entity", "basic_entity_inherited_key", "weak_entity",
    "one_many_relationship", "many_many_relationship", "reflexive_many_many_relationship",
}


def _load_module(path: Path, name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _norm_chart(s: str) -> str:
    return " ".join(str(s).lower().replace("-", " ").split())


def _gold_pattern_tokens(expected: str) -> set[str]:
    """Extract taxonomy tokens present in a gold expected_pattern string (handles 'a / b' and 'n/a')."""
    e = expected.lower()
    return {tok for tok in TAXONOMY if tok in e}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["auto", "full", "deterministic"], default="auto")
    ap.add_argument("--datasource", choices=["json", "postgres", "config"], default="json",
                    help="json = offline Mondial files (default); postgres = same live DB as the "
                         "web (needs sqlalchemy+psycopg2 and the DB running, no web server); "
                         "config = respect .env as-is.")
    ap.add_argument("--samples", type=int, default=1,
                    help="self-consistency samples for the NL parser (>1 enables majority vote).")
    ap.add_argument("--temperature", type=float, default=0.0,
                    help="sampling temperature for the NL parser (used when --samples > 1).")
    ap.add_argument("--from", dest="from_n", type=int, default=1,
                    help="1-based task index to (re)run from; earlier tasks are reused from the "
                         "existing --out file if present (resume without re-spending quota).")
    ap.add_argument("--gold", default=str(HERE / "gold.json"))
    ap.add_argument("--out", default=str(HERE / "results.json"))
    args = ap.parse_args()

    # Pick the data source. 'config' respects .env (defaults to postgres); the other two force it.
    if args.datasource != "config":
        os.environ["VIZER_DATASOURCE"] = args.datasource

    from config import load_config
    from datasource import make_datasource
    import geodetect

    cfg = load_config()

    # Decide mode: full needs both the openai lib and a key.
    have_openai = True
    try:
        import openai  # noqa: F401
    except Exception:
        have_openai = False
    mode = args.mode
    if mode == "auto":
        mode = "full" if (have_openai and cfg.has_llm) else "deterministic"
    if mode == "full" and not (have_openai and cfg.has_llm):
        print("[warn] full mode requested but " +
              ("openai not installed" if not have_openai else "no DASHSCOPE key") +
              " -> falling back to deterministic.")
        mode = "deterministic"

    print("=== NL->viz local evaluation ===")
    print("mode:", mode, "| openai:", have_openai, "| key:", cfg.has_llm,
          "| datasource:", cfg.datasource, "\n")

    ds = make_datasource(cfg)
    schema = ds.get_schema()
    tables = ds.tables_view()
    # Inject heuristic geo columns (no LLM) so choropleth/word-cloud eligibility matches the server.
    geodetect.inject(schema, geodetect.geo_columns(schema))

    STEP1 = _load_module(EXP / "results" / "prompt_v9_codegen" / "gpt_generated.py", "step1")
    STEP2 = _load_module(EXP / "results" / "step2_codegen" / "gpt_recommend_charts.py", "step2")

    nl_parse = None
    if mode == "full":
        from nlquery.nl_to_selection import parse as nl_parse  # noqa: N816

    gold = json.loads(Path(args.gold).read_text("utf-8"))
    tasks = gold["tasks"]

    rows_out = []

    # Resume support: tasks before --from are reused from the existing --out file (so a partial /
    # quota-limited run is not repeated). Scoring is computed at the end over rows_out, so reused
    # and freshly-run entries count identically.
    prev: dict = {}
    if args.from_n > 1 and Path(args.out).exists():
        try:
            prev = {r["id"]: r for r in json.loads(Path(args.out).read_text("utf-8")).get("tasks", [])}
        except Exception:  # noqa: BLE001
            prev = {}

    for idx, t in enumerate(tasks, 1):
        tid, nl = t["id"], t["nl_input"]
        if idx < args.from_n:
            r = prev.get(tid)
            if r is not None:
                rows_out.append(r)
                print(f"[{idx}/{len(tasks)}] {tid}: reused prior result "
                      f"(table={r.get('selection',{}).get('table')})", flush=True)
            else:
                print(f"[{idx}/{len(tasks)}] {tid}: skipped (no prior result to reuse)", flush=True)
            continue
        print(f"[{idx}/{len(tasks)}] {tid}: parsing …", flush=True)
        gold_table = t["expected_table"]
        gold_cols = t["expected_columns"]
        gp_tokens = _gold_pattern_tokens(t["expected_pattern"])
        primary = _norm_chart(t["expected_charts"]["primary"])
        acceptable = {_norm_chart(c) for c in t["expected_charts"].get("acceptable", [])}
        expected_hard = (not gp_tokens)      # D5/D6 style: no clean taxonomy token in gold

        rec: dict = {"id": tid, "nl": nl, "mode": mode}

        # --- selection ---
        if mode == "full":
            try:
                pr = nl_parse(nl, schema, samples=args.samples, temperature=args.temperature)
                sel = (pr or {}).get("selection") or {}
                rec["vote"] = (pr or {}).get("vote")
                table = sel.get("table")
                columns = sel.get("columns") or []
                rec["parsed_ok"] = bool(pr and pr.get("ok"))
                rec["parse_error"] = (pr or {}).get("error", "")
                rec["filters"] = sel.get("filters")
                rec["joins"] = sel.get("joins")
                rec["aggregate"] = sel.get("aggregate")
            except Exception as exc:  # noqa: BLE001
                table, columns = None, []
                rec["parsed_ok"] = False
                rec["parse_error"] = "exception: " + str(exc)
            # selection scored only in full mode
            table_hit = (table == gold_table)
            col_hit = table_hit and set(gold_cols).issubset(set(columns or []))
            sel_pass = bool(col_hit)
            rec["selection"] = {"table": table, "columns": columns,
                                "table_hit": table_hit, "cols_superset": col_hit, "pass": sel_pass}
        else:
            table, columns = gold_table, gold_cols
            rec["selection"] = {"table": table, "columns": columns, "note": "NL skipped (gold selection)"}

        # --- pattern (Step 1) ---
        predicted = ""
        if table and columns:
            try:
                predicted = STEP1.classify_selection(schema, table, columns).get("predicted_pattern", "")
            except Exception as exc:  # noqa: BLE001
                predicted = "error:" + str(exc)
        rec["predicted_pattern"] = predicted
        rec["gold_pattern"] = t["expected_pattern"]
        if not expected_hard:
            rec["pattern_pass"] = predicted in gp_tokens
        else:
            rec["pattern_pass"] = None   # expected-hard: reported, not scored

        # --- charts (Step 2, deterministic candidates) ---
        recommended = []
        eligible = []
        if table and columns and predicted in TAXONOMY:
            try:
                s2 = STEP2.recommend(schema, table, columns, predicted, rows=tables.get(table))
                recommended = [ _norm_chart(c) for c in (s2.get("recommended_charts") or []) ]
                eligible = [ _norm_chart(c.get("chart")) for c in (s2.get("candidates") or [])
                             if c.get("eligible") ]
            except Exception as exc:  # noqa: BLE001
                rec["step2_error"] = str(exc)
        pool = set(recommended) | set(eligible)
        rec["recommended_charts"] = sorted(pool)
        primary_hit = primary in pool
        acceptable_hit = bool(acceptable & pool)
        if not expected_hard:
            rec["chart_pass"] = primary_hit or acceptable_hit
            rec["chart_primary_hit"] = primary_hit
        else:
            rec["chart_pass"] = None
            rec["chart_primary_hit"] = primary_hit
        rec["gold_chart_primary"] = primary
        rec["david_result"] = t["david_result"]
        rec["expected_hard"] = expected_hard
        rows_out.append(rec)
        seltxt = (f"table={rec['selection'].get('table')} cols={rec['selection'].get('columns')}"
                  if mode == "full" else "gold selection")
        print(f"        -> {seltxt} | pattern={predicted or '(none)'} | "
              f"charts={rec['recommended_charts']}", flush=True)

    # ---- score (computed over rows_out so reused + freshly-run entries count identically) ----
    sel_ok = sum(1 for r in rows_out if r.get("selection", {}).get("pass") is True)
    sel_total = sum(1 for r in rows_out if r.get("selection", {}).get("pass") is not None)
    pat_ok = sum(1 for r in rows_out if r.get("pattern_pass") is True)
    pat_total = sum(1 for r in rows_out if r.get("pattern_pass") is not None)
    chart_ok = sum(1 for r in rows_out if r.get("chart_pass") is True)
    chart_total = sum(1 for r in rows_out if r.get("chart_pass") is not None)

    # ---- report ----
    def pct(a, b):
        return f"{a}/{b} = {100*a/b:.0f}%" if b else "n/a"

    print(f"{'ID':<4}{'Sel':<5}{'Pat':<5}{'Chart':<6}  predicted_pattern / gold          chart hit")
    print("-" * 96)
    for r in rows_out:
        def mark(v):
            return "—" if v is None else ("P" if v else "F")
        sel = mark(r["selection"].get("pass")) if mode == "full" else "·"
        pp = r["predicted_pattern"] or "(none)"
        gp = r["gold_pattern"]
        chit = ("primary" if r["chart_primary_hit"] else
                ("accept" if r["chart_pass"] else ("—" if r["chart_pass"] is None else "miss")))
        flag = "  [expected-hard/David-fail]" if r["expected_hard"] else ""
        print(f"{r['id']:<4}{sel:<5}{mark(r['pattern_pass']):<5}{mark(r['chart_pass']):<6}  "
              f"{pp:<28} vs {gp[:22]:<22}  {chit}{flag}")

    print("\n=== summary (expected-hard D5/D6 excluded from rates) ===")
    if mode == "full":
        print("NL selection accuracy :", pct(sel_ok, sel_total))
    else:
        print("NL selection accuracy : (skipped — deterministic mode; run with openai for this)")
    print("Pattern accuracy      :", pct(pat_ok, pat_total))
    print("Chart accuracy        :", pct(chart_ok, chart_total))
    print("(David Bull reference : 11/13 overall; 2 failed = D5, D6)")

    Path(args.out).write_text(json.dumps(
        {"mode": mode, "summary": {
            "selection": [sel_ok, sel_total] if mode == "full" else None,
            "pattern": [pat_ok, pat_total], "chart": [chart_ok, chart_total]},
         "tasks": rows_out}, indent=2), "utf-8")
    print("\nwrote", args.out)


if __name__ == "__main__":
    main()
