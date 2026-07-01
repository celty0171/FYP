"""Deterministic Step 1->2->3 pipeline web front-end (no model calls).

Wires three deterministic programs together:
  Step 1  pattern identification : results/prompt_v9_codegen/gpt_generated.py
  Step 2  chart recommend + map  : results/step2_codegen/gpt_recommend_charts.py
  Step 3  visualisation render   : results/viz_codegen_*/render_*_reference.py

A column selection flows: classify -> recommend -> render the chosen chart's mapping
against mondial_data.json. Charts without a renderer yet return "working in process".

Standard library only. Run:
    python experiments/web_pipeline/server.py --port 8090
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

EXP = Path(__file__).resolve().parents[1]          # experiments/
HERE = Path(__file__).resolve().parent
WORKING = "working in process"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


SCHEMA = json.loads((EXP / "mondial_database" / "mondial_schema_summary_clean.json").read_text("utf-8"))
DATA = json.loads((EXP / "mondial_database" / "mondial_data.json").read_text("utf-8"))

STEP1 = _load(EXP / "results" / "prompt_v9_codegen" / "gpt_generated.py", "step1_classifier")
STEP2 = _load(EXP / "results" / "step2_codegen" / "gpt_recommend_charts.py", "step2_recommender")

# chart-name (lower-case) -> renderer module file
RENDERER_PATHS = {
    "bar chart": "viz_codegen_bar/render_bar_reference.py",
    "scatter diagram": "viz_codegen_scatterbubble/render_scatterbubble_reference.py",
    "bubble chart": "viz_codegen_scatterbubble/render_scatterbubble_reference.py",
    "calendar chart": "viz_codegen_calendar/render_calendar_reference.py",
    "tree map": "viz_codegen_treemap/render_treemap_reference.py",
    "circle packing": "viz_codegen_circlepack/render_circlepack_reference.py",
    "hierarchy tree": "viz_codegen_hierarchytree/render_hierarchytree_reference.py",
    "sankey diagram": "viz_codegen_sankey_d3/render_sankey_reference.py",
    "chord diagram": "viz_codegen_chord/render_chord_reference.py",
    "matrix heatmap": "viz_codegen_matrix/render_matrix_reference.py",
    "force graph": "viz_codegen_force/render_force_reference.py",
    "arc diagram": "viz_codegen_arc/render_arc_reference.py",
    "line chart": "viz_codegen_weak/render_line_reference.py",
    "stacked bar chart": "viz_codegen_weak/render_stacked_reference.py",
    "grouped bar chart": "viz_codegen_weak/render_grouped_reference.py",
    "spider chart": "viz_codegen_weak/render_spider_reference.py",
    "choropleth map": "viz_codegen_choropleth/render_choropleth_reference.py",
    "word cloud": "viz_codegen_wordcloud/render_wordcloud_reference.py",
}
RENDERERS = {
    name: _load(EXP / "results" / path, "r_" + name.replace(" ", "_"))
    for name, path in RENDERER_PATHS.items()
}


def render_chart(chart: str | None, mapping: dict[str, Any]) -> dict[str, Any]:
    """Render a chart from its Step-2 mapping, or report it's not built yet."""
    key = (chart or "").strip().lower()
    mod = RENDERERS.get(key)
    if mod is None or not mapping:
        return {"chart": chart, "available": False, "html": WORKING}
    try:
        rows = mod._rows_for(mapping, DATA)
        html = mod.render(mapping, rows)
        return {"chart": chart, "available": True, "html": html}
    except Exception as exc:  # keep the UI alive on a bad mapping
        return {"chart": chart, "available": False, "html": "render error: " + str(exc)}


def run_pipeline(table: str, columns: list[str]) -> dict[str, Any]:
    s1 = STEP1.classify_selection(SCHEMA, table, columns)
    pattern = s1["predicted_pattern"]
    # Pass the selected table's rows so the Step-2 relationship selector can measure
    # density / N / symmetric (and weak-entity completeness) live.
    rows = DATA.get("tables", {}).get(table)
    s2 = STEP2.recommend(SCHEMA, table, columns, pattern, rows=rows)
    selected = s2.get("selected") or {}
    rendered = render_chart(selected.get("chart"), selected.get("mapping") or {})
    return {
        "selected_table": table,
        "selected_columns": columns,
        "step1": {"pattern": pattern, "reason": s1.get("reason", "")},
        "step2": {
            "recommended_charts": s2.get("recommended_charts", []),
            "candidates": s2.get("candidates", []),
            "selected": selected,
        },
        "step3": rendered,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: Any, ctype: str = "application/json") -> None:
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/schema":
            tables = {t: [c["name"] for c in SCHEMA["tables"][t]["columns"]] for t in sorted(SCHEMA["tables"])}
            self._send(200, {"tables": tables})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self._read_json()
            if self.path == "/api/run":
                table = (body.get("table") or "").strip()
                columns = body.get("columns") or []
                if not table or not columns:
                    self._send(400, {"error": "pick a table and at least one column"})
                    return
                self._send(200, run_pipeline(table, columns))
            elif self.path == "/api/render":
                self._send(200, render_chart(body.get("chart"), body.get("mapping") or {}))
            else:
                self._send(404, {"error": "not found"})
        except Exception as exc:
            self._send(500, {"error": str(exc)})

    def log_message(self, *args: Any) -> None:  # quiet
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    print(f"Pipeline front-end on http://{args.host}:{args.port}  (renderers: {', '.join(sorted(RENDERERS))})")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
