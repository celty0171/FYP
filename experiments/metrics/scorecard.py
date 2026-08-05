"""Layout-quality scorecard for arc / chord / sankey / force on the Mondial relations.

Renders each chart with its active renderer, extracts the emitted layout, and computes the
Purchase/Dunne metrics (crossings + [0,1] scores, spans, node occlusion). Prints a table and
optionally writes a markdown report; supports before/after comparison against a saved baseline.

Usage:
    python experiments/metrics/scorecard.py                       # print scorecard
    python experiments/metrics/scorecard.py --baseline base.json  # also save a snapshot
    python experiments/metrics/scorecard.py --compare base.json   # print deltas vs a snapshot
    python experiments/metrics/scorecard.py --report report.md    # also write markdown
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(HERE))          # so layout_metrics can import spring_layout
import layout_metrics as LM            # noqa: E402

RESULTS = EXP / "results"
DATA = json.loads((EXP / "mondial_database" / "mondial_data.json").read_text("utf-8"))["tables"]

# relation -> selection fields
RELATIONS = {
    "borders":     dict(table="borders", source="country1", target="country2",
                        scalar="length", pattern="reflexive_many_many_relationship"),
    "encompasses": dict(table="encompasses", source="country", target="continent",
                        scalar="percentage", pattern="many_many_relationship"),
    "merges_with": dict(table="merges_with", source="sea1", target="sea2",
                        scalar=None, pattern="reflexive_many_many_relationship"),
}


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# chart -> (renderer path, mapping builder, metric fn, applies(relation)->bool)
def _arc_map(r):    return dict(table=r["table"], source=r["source"], target=r["target"],
                                value=r["scalar"] or "count", pattern=r["pattern"])
def _chord_map(r):  return dict(table=r["table"], source=r["source"], target=r["target"],
                                width=r["scalar"], pattern=r["pattern"])
def _sankey_map(r): return dict(table=r["table"], source=r["source"], target=r["target"],
                                width=r["scalar"])
def _force_map(r):  return dict(table=r["table"], source=r["source"], target=r["target"],
                                value=r["scalar"] or "count", pattern=r["pattern"])

CHARTS = {
    "arc":    (RESULTS / "viz_codegen_arc/sonnet_arc.py", _arc_map, LM.arc_metrics,
               lambda r: "reflexive" in r["pattern"]),
    "chord":  (RESULTS / "viz_codegen_chord/sonnet_chord.py", _chord_map, LM.chord_metrics,
               lambda r: r["scalar"] is not None),
    "sankey": (RESULTS / "viz_codegen_sankey_d3/sonnet_sankey.py", _sankey_map, LM.sankey_metrics,
               lambda r: r["scalar"] is not None),
    "force":  (RESULTS / "viz_codegen_force/sonnet_force.py", _force_map, LM.force_metrics,
               lambda r: True),
}


def collect() -> list[dict]:
    rows = []
    for chart, (path, build, metric, applies) in CHARTS.items():
        mod = _load(path)
        for rname, r in RELATIONS.items():
            if not applies(r):
                continue
            data = DATA.get(r["table"], [])
            try:
                html = mod.render(build(r), data)
                m = metric(html)
            except Exception as exc:  # noqa: BLE001
                m = {"chart": chart, "error": str(exc)[:60]}
            m["relation"] = rname
            m["key"] = chart + "/" + rname
            rows.append(m)
    return rows


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


COLS = ["nodes", "edges", "crossings", "crossing_score", "max_span",
        "node_occlusion", "occlusion_score", "min_crossing_angle"]


def print_table(rows, baseline=None):
    base = {b["key"]: b for b in baseline} if baseline else {}
    hdr = ["chart/relation"] + COLS
    print("  ".join(h.ljust(15) for h in hdr))
    print("-" * (17 * len(hdr)))
    for m in rows:
        line = [m["key"].ljust(15)]
        for c in COLS:
            cur = m.get(c)
            cell = _fmt(cur)
            if base and m["key"] in base and isinstance(cur, (int, float)) and isinstance(base[m["key"]].get(c), (int, float)):
                delta = cur - base[m["key"]][c]
                if abs(delta) > 1e-9:
                    cell += f" ({'+' if delta > 0 else ''}{_fmt(delta)})"
            line.append(cell.ljust(15))
        print("  ".join(line))
        if "error" in m:
            print("      ! " + m["error"])


def write_report(rows, path: Path):
    lines = ["# Layout-quality scorecard\n",
             "Metrics: edge **crossings** (Purchase) and Dunne & Shneiderman `[0,1]` scores "
             "(1 = best). `crossing_score = 1 − crossings/max_possible`; `occlusion_score = 1 − "
             "overlapping-node-pairs/all-pairs`. Targets: crossing_score high, occlusion_score ≈ 1.\n",
             "| chart / relation | nodes | edges | crossings | crossing_score | max_span | occlusion | occ_score | min∠ |",
             "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for m in rows:
        lines.append("| " + " | ".join(_fmt(m.get(c)) for c in
                     ["key", "nodes", "edges", "crossings", "crossing_score", "max_span",
                      "node_occlusion", "occlusion_score", "min_crossing_angle"]) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", help="save the current metrics to this JSON")
    ap.add_argument("--compare", help="print deltas against this saved JSON")
    ap.add_argument("--report", help="write a markdown report to this path")
    args = ap.parse_args()

    rows = collect()
    baseline = json.loads(Path(args.compare).read_text()) if args.compare else None
    print_table(rows, baseline)
    if args.baseline:
        Path(args.baseline).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print("saved baseline ->", args.baseline)
    if args.report:
        write_report(rows, Path(args.report))


if __name__ == "__main__":
    main()
