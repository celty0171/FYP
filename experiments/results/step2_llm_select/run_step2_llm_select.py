"""Offline comparison: LLM chart selection vs the deterministic rule pick (Step 2).

For each of the 9 blind cases this runs the deterministic Step-2 recommender to get the
eligible candidates + rule-selected chart, then (if an LLM is configured) asks the
``chartselect`` selector to pick and justify one candidate. Both picks are scored against
the gold ``expected_visualisations`` — **gold is read only here, after both predictions are
made**, so the blind/gold separation the selector relies on is preserved.

Outputs (under this directory):
  responses/case_<id>.json   per-case det + llm picks (no gold)
  comparison.json            per-case det_chart / llm_chart / gold / hits / agreement
  SUMMARY.md                 hit-rates, agreement, and any degraded-mode note

Run:
  python experiments/results/step2_llm_select/run_step2_llm_select.py            # live LLM if key set
  python experiments/results/step2_llm_select/run_step2_llm_select.py --no-llm   # rule-only dry run
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]                    # experiments/
DB = EXP / "mondial_database"
if str(EXP) not in sys.path:
    sys.path.insert(0, str(EXP))


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Natural-language query examples (A1: intent-aware selection). Each is free text that is
# also the user's *goal* — the NL parser turns it into a selection, then Step 1/2 + the
# intent-aware selector choose the chart. They span different tables, chart families and
# intents so you can see the goal steer the pick. `targets` is a human note only (never sent
# to the model); the parser/classifier/selector decide everything from the text + schema.
NL_EXAMPLES = [
    {"id": "nl1_correlation",
     "query": "I want to see how GDP relates to unemployment across countries",
     "targets": "economy · correlation intent → scatter"},
    {"id": "nl2_compare",
     "query": "Compare the total population of each country",
     "targets": "country · comparison/ranking intent → bar"},
    {"id": "nl3_geo",
     "query": "Show each country's population on a world map",
     "targets": "country · geospatial intent → choropleth"},
    {"id": "nl4_trend",
     "query": "Show how each country's population has changed over the years",
     "targets": "country_population · trend-over-time (weak entity) → line"},
    {"id": "nl5_relationship",
     "query": "Show which countries border each other and how long each border is",
     "targets": "borders · relationship/flow (many-many) → sankey/chord"},
    {"id": "nl6_distribution",
     "query": "Compare lakes by their elevation and depth",
     "targets": "lake · distribution of two scalars → scatter/bubble"},
]


def _build_client(no_llm: bool):
    """Return (client, note). client is None when disabled/unavailable."""
    if no_llm:
        return None, "--no-llm: rule pick only."
    try:
        from config import load_config
        from nlquery.bailian_client import BailianClient
        cfg = load_config()
        if cfg.has_llm:
            return BailianClient(api_key=cfg.dashscope_api_key,
                                 base_url=cfg.dashscope_base_url,
                                 model=cfg.step2_model), ""
        return None, "no DASHSCOPE_API_KEY set — LLM picks fell back to the rule pick."
    except Exception as exc:  # noqa: BLE001
        return None, "LLM client unavailable (" + str(exc) + ") — fell back to the rule pick."


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["blind", "nl", "both"], default="both",
                    help="blind = 9-case rule-vs-LLM comparison; nl = natural-language examples "
                         "(needs an API key); both = run each in turn.")
    ap.add_argument("--cases", default=str(EXP / "results" / "step2_codegen" / "cases_with_pattern.json"))
    ap.add_argument("--schema", default=str(DB / "mondial_schema_summary_clean.json"))
    ap.add_argument("--data", default=str(DB / "mondial_data.json"))
    ap.add_argument("--gold", default=str(EXP / "inputs" / "mondial_gold_patterns.json"))
    ap.add_argument("--out", default=str(HERE))
    ap.add_argument("--no-llm", action="store_true", help="skip the LLM; score the rule pick only")
    args = ap.parse_args()

    STEP2 = _load_module(EXP / "results" / "step2_codegen" / "gpt_recommend_charts.py", "step2_recommender")
    from chartselect import select as llm_select

    schema = _load_json(Path(args.schema))
    data = _load_json(Path(args.data))["tables"]
    client, llm_note = _build_client(args.no_llm)

    if args.mode in ("blind", "both"):
        run_blind(args, STEP2, llm_select, schema, data, client, llm_note)
    if args.mode in ("nl", "both"):
        run_nl(args, STEP2, llm_select, schema, data, client)


def run_nl(args, STEP2, llm_select, schema, data, client) -> None:
    """Run the natural-language examples: parse -> classify -> recommend -> intent-aware select."""
    print("\n" + "=" * 70 + "\nNATURAL-LANGUAGE QUERY EXAMPLES (intent-aware Step 2)\n" + "=" * 70)
    if client is None:
        print("skipped: NL parsing needs an LLM. Set DASHSCOPE_API_KEY in .env and drop --no-llm.")
        return

    STEP1 = _load_module(EXP / "results" / "prompt_v9_codegen" / "gpt_generated.py", "step1_classifier")
    from nlquery.nl_to_selection import parse as nl_parse

    out = []
    for ex in NL_EXAMPLES:
        q = ex["query"]
        print("\n--- " + ex["id"] + " ---")
        print("query : " + q)
        print("target: " + ex["targets"])
        res = nl_parse(q, schema, client=client)
        if not res.get("ok"):
            print("  parse failed: " + str(res.get("error")))
            out.append({"id": ex["id"], "query": q, "error": res.get("error")})
            continue
        sel = res["selection"]
        table, cols = sel["table"], sel["columns"]
        rows = data.get(table, [])
        pattern = STEP1.classify_selection(schema, table, cols).get("predicted_pattern", "")
        s2 = STEP2.recommend(schema, table, cols, pattern, rows=rows)
        det_chart = (s2.get("selected") or {}).get("chart")
        pick = llm_select(schema, table, cols, pattern, s2, client=client, rows=rows, intent=q)

        print("  parsed  : {} {}".format(table, cols))
        print("  pattern : {}".format(pattern))
        print("  candidates: {}".format(s2.get("recommended_charts", [])))
        print("  rule pick : {}".format(det_chart))
        print("  LLM pick  : {}  [{}]".format(pick.get("recommended_chart"), pick.get("source")))
        print("  reason    : {}".format(pick.get("reason", "")))
        for r in pick.get("ranking", []):
            if r.get("note"):
                print("     - {}: {}".format(r["chart"], r["note"]))
        out.append({
            "id": ex["id"], "query": q, "targets": ex["targets"],
            "parsed_table": table, "parsed_columns": cols, "pattern": pattern,
            "candidates": s2.get("recommended_charts", []),
            "rule_pick": det_chart,
            "llm": {"recommended_chart": pick.get("recommended_chart"),
                    "reason": pick.get("reason", ""), "ranking": pick.get("ranking", []),
                    "mapping": pick.get("mapping"), "source": pick.get("source")},
        })

    out_path = Path(args.out) / "nl_examples_output.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"examples": out}, f, indent=2, ensure_ascii=False)
    print("\nwrote " + str(len(out)) + " NL example results to " + str(out_path))


def run_blind(args, STEP2, llm_select, schema, data, client, llm_note) -> None:
    from scripts.evaluate_llm_run import normalise_label  # gold-agnostic label normaliser
    cases = _load_json(Path(args.cases)).get("cases", [])
    resp_dir = Path(args.out) / "responses"
    resp_dir.mkdir(parents=True, exist_ok=True)

    predictions = []  # (case_id, table, cols, pattern, det_chart, llm_chart, llm_source)
    for case in cases:
        cid = case["case_id"]
        table = case["selected_table"]
        cols = case["selected_columns"]
        pattern = case["identified_pattern"]
        rows = data.get(table, [])

        s2 = STEP2.recommend(schema, table, cols, pattern, rows=rows)
        det_chart = (s2.get("selected") or {}).get("chart")

        # Blind cases carry no user goal, so intent="" — the data-shape signals still apply.
        pick = llm_select(schema, table, cols, pattern, s2, client=client, rows=rows, intent="")
        llm_chart = pick.get("recommended_chart")
        llm_reason = pick.get("reason", "")

        with open(resp_dir / ("case_" + str(cid) + ".json"), "w", encoding="utf-8") as f:
            json.dump({
                "case_id": cid,
                "selected_table": table,
                "selected_columns": cols,
                "identified_pattern": pattern,
                "deterministic": {
                    "recommended_charts": s2.get("recommended_charts", []),
                    "selected": s2.get("selected"),
                },
                "llm": {
                    "recommended_chart": llm_chart,
                    "reason": pick.get("reason", ""),
                    "ranking": pick.get("ranking", []),
                    "mapping": pick.get("mapping"),
                    "source": pick.get("source"),
                },
            }, f, indent=2, ensure_ascii=False)

        predictions.append((cid, table, cols, pattern, det_chart, llm_chart, pick.get("source"), llm_reason))

    # --- Scoring: gold is loaded ONLY now, after every prediction is written. ---
    gold_cases = _load_json(Path(args.gold)).get("cases", [])
    gold_by_pos = list(gold_cases)  # cases align 1:1 by order with cases_with_pattern.json

    rows_out = []
    det_hits = llm_hits = agree = llm_from_model = 0
    for i, (cid, table, cols, pattern, det_chart, llm_chart, source, llm_reason) in enumerate(predictions):
        gold = gold_by_pos[i] if i < len(gold_by_pos) else {}
        gold_set = {normalise_label(v) for v in gold.get("expected_visualisations", [])}
        det_n = normalise_label(det_chart) if det_chart else ""
        llm_n = normalise_label(llm_chart) if llm_chart else ""
        det_hit = det_n in gold_set
        llm_hit = llm_n in gold_set
        det_hits += det_hit
        llm_hits += llm_hit
        agree += (det_n == llm_n)
        llm_from_model += (source == "llm")
        rows_out.append({
            "case_id": cid, "table": table, "columns": cols, "pattern": pattern,
            "gold_visualisations": sorted(gold_set),
            "det_chart": det_chart, "det_norm": det_n, "det_hit": det_hit,
            "llm_chart": llm_chart, "llm_norm": llm_n, "llm_hit": llm_hit,
            "llm_source": source, "llm_reason": llm_reason, "agree": det_n == llm_n,
        })

    n = len(predictions)
    summary = {
        "n_cases": n,
        "deterministic_hits": det_hits,
        "llm_hits": llm_hits,
        "agreement": agree,
        "llm_answered_by_model": llm_from_model,
        "note": llm_note,
        "cases": rows_out,
    }
    with open(Path(args.out) / "comparison.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    _write_summary_md(Path(args.out) / "SUMMARY.md", summary)
    print("wrote", n, "responses + comparison.json + SUMMARY.md to", args.out)
    print("rule hits: {}/{}  llm hits: {}/{}  agreement: {}/{}  (llm answered {}/{})".format(
        det_hits, n, llm_hits, n, agree, n, llm_from_model, n))
    if llm_note:
        print("note:", llm_note)


def _write_summary_md(path: Path, s: dict) -> None:
    n = s["n_cases"]
    lines = [
        "# Step 2 — LLM chart selection vs deterministic rule pick",
        "",
        "Offline comparison over the {} blind cases. Both picks are scored against the gold ".format(n),
        "`expected_visualisations` (a hit = the picked chart is in the gold set, after alias ",
        "normalisation). Gold is read only during scoring, after predictions are written, so the ",
        "selector never sees it.",
        "",
        "| metric | value |",
        "|---|---|",
        "| cases | {} |".format(n),
        "| deterministic (rule) hits | {}/{} |".format(s["deterministic_hits"], n),
        "| LLM hits | {}/{} |".format(s["llm_hits"], n),
        "| rule/LLM agreement | {}/{} |".format(s["agreement"], n),
        "| LLM answered by model | {}/{} |".format(s["llm_answered_by_model"], n),
        "",
    ]
    if s.get("note"):
        lines += ["> **Note:** " + s["note"], ""]
    lines += [
        "| case | pattern | gold | rule pick | ✓ | LLM pick | ✓ | src | reason |",
        "|---|---|---|---|:-:|---|:-:|---|---|",
    ]
    for c in s["cases"]:
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            c["case_id"], c["pattern"], ", ".join(c["gold_visualisations"]) or "—",
            c["det_chart"] or "—", "✓" if c["det_hit"] else "·",
            c["llm_chart"] or "—", "✓" if c["llm_hit"] else "·",
            c["llm_source"] or "—", (c.get("llm_reason") or "").replace("|", "\\|")))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
