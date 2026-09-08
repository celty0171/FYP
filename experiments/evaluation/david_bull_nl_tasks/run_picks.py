#!/usr/bin/env python3
"""Capture the LLM 'best chart' pick for the 13 David-Bull tasks.

Reuses the recorded selections + identified patterns from results_pg_full_v2.json (so the
candidate sets match Table 5.4 and no NL-parse quota is re-spent), rebuilds the Step-2
candidates on the live Postgres data, and asks the deployed LLM chart-selector to pick one.

API guard: probes the DashScope API once before running and ABORTS if it is unavailable /
out of quota, and aborts again if any per-task selector call falls back to the deterministic
path (which would mean the API failed mid-run). It never silently records a fallback pick.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]                        # experiments/
sys.path.insert(0, str(EXP))
sys.path.insert(0, str(EXP / "results" / "prompt_v9_codegen"))

os.environ["VIZER_DATASOURCE"] = "postgres"  # match the run that produced results_pg_full_v2.json

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


def main() -> None:
    from config import load_config
    from datasource import make_datasource
    import geodetect
    from nlquery.bailian_client import BailianClient
    from chartselect import llm_chart_selector as selector

    cfg = load_config()
    if not cfg.has_llm:
        print("ABORT: no DASHSCOPE key configured (cfg.has_llm is False).")
        sys.exit(2)

    ds = make_datasource(cfg)
    schema = ds.get_schema()
    tables = ds.tables_view()
    geodetect.inject(schema, geodetect.geo_columns(schema))
    STEP2 = _load_module(EXP / "results" / "step2_codegen" / "gpt_recommend_charts.py", "step2")

    # --- API guard: one cheap probe call; abort if it fails (no key / quota / network). ---
    client = BailianClient(cfg.dashscope_api_key, cfg.dashscope_base_url, cfg.step2_model)
    print("Probing API (model=%s) ..." % cfg.step2_model, flush=True)
    try:
        client.chat_json("You reply only with JSON.", 'Return exactly {"ok": true}')
    except Exception as exc:  # noqa: BLE001
        print("ABORT: API probe failed — no API / quota exhausted. Detail:", exc)
        sys.exit(3)
    print("API probe OK.\n", flush=True)

    v2 = json.loads((HERE / "results_pg_full_v2.json").read_text("utf-8"))["tasks"]

    out = []
    for t in v2:
        tid = t["id"]
        sel = t.get("selection") or {}
        table = sel.get("table")
        cols = sel.get("columns") or []
        pat = t.get("predicted_pattern") or ""
        nl = t.get("nl") or ""
        if not table or pat not in TAXONOMY:
            out.append({"id": tid, "table": table, "pattern": pat, "pick": None,
                        "note": "no scorable pattern/selection"})
            print("%-4s (skipped: pattern=%s)" % (tid, pat or "none"), flush=True)
            continue

        rows = tables.get(table)
        s2 = STEP2.recommend(schema, table, cols, pat, rows=rows)
        cands = [c.get("chart") for c in (s2.get("candidates") or []) if c.get("eligible")]
        res = selector.select(schema, table, cols, pat, s2, client=client, rows=rows, intent=nl)

        if res.get("source") != "llm":
            print("ABORT: selector fell back to deterministic on %s — API likely failed mid-run. "
                  "Detail: %s" % (tid, res.get("error")))
            sys.exit(4)

        out.append({
            "id": tid, "table": table, "pattern": pat, "candidates": cands,
            "pick": res.get("recommended_chart"), "reason": res.get("reason"),
            "source": res.get("source"),
        })
        print("%-4s pick=%-16s from %s" % (tid, res.get("recommended_chart"), cands), flush=True)

    (HERE / "picks_v2.json").write_text(json.dumps(out, indent=2), "utf-8")
    print("\nWrote", HERE / "picks_v2.json")


if __name__ == "__main__":
    main()
