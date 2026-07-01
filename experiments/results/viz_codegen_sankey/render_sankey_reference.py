"""Deterministic Sankey renderer for many_many_relationship selections.

Reference implementation of the renderer elicited by
prompts/viz_codegen_sankey_prompt.md. Reads a chart mapping and the relationship
rows at run time and emits a complete, standalone Google Charts Sankey HTML file.
Data is injected by the program, so completeness is structural. Std-lib only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _encoding(mapping: dict[str, Any]) -> dict[str, str]:
    """Accept either a bare {source,target,width} mapping or a full Stage-1/2 result."""
    if {"source", "target", "width"} <= set(mapping):
        return {k: mapping[k] for k in ("source", "target", "width")}
    for key in ("chart_mapping",):
        sub = mapping.get(key)
        if isinstance(sub, dict) and {"source", "target", "width"} <= set(sub):
            return {k: sub[k] for k in ("source", "target", "width")}
    sel = mapping.get("selected_visualisation", {})
    enc = sel.get("encoding") if isinstance(sel, dict) else None
    if isinstance(enc, dict) and {"source", "target", "width"} <= set(enc):
        return {k: enc[k] for k in ("source", "target", "width")}
    raise ValueError("mapping must provide source/target/width (directly or via chart_mapping/encoding)")


def render(mapping: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    enc = _encoding(mapping)
    s_col, t_col, w_col = enc["source"], enc["target"], enc["width"]

    # Sum duplicate (source, target) pairs into a single flow; preserve first-seen order.
    flows: dict[tuple[str, str], float] = {}
    order: list[tuple[str, str]] = []
    for row in rows:
        if s_col not in row or t_col not in row or w_col not in row:
            continue
        key = (str(row[s_col]), str(row[t_col]))
        try:
            weight = float(row[w_col])
        except (TypeError, ValueError):
            continue
        if key not in flows:
            flows[key] = 0.0
            order.append(key)
        flows[key] += weight

    links = [[s, t, flows[(s, t)]] for (s, t) in order]
    title = mapping.get("title") or f"{s_col} → {t_col} Sankey diagram"

    data_json = json.dumps(links)
    rows_count = len(links)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<script type="text/javascript" src="https://www.gstatic.com/charts/loader.js"></script>
<style>
  body {{ font-family: Arial, sans-serif; margin: 16px; }}
  h1 {{ font-size: 18px; }}
  #sankey {{ width: 1100px; height: {max(400, rows_count * 16)}px; }}
</style>
<script type="text/javascript">
  google.charts.load('current', {{'packages':['sankey']}});
  google.charts.setOnLoadCallback(drawChart);

  // Each link: [source, target, width]. Injected by the renderer; not truncated.
  var links = {data_json};

  function drawChart() {{
    var data = new google.visualization.DataTable();
    data.addColumn('string', '{s_col}');
    data.addColumn('string', '{t_col}');
    data.addColumn('number', '{w_col}');
    data.addRows(links);

    var options = {{
      width: 1100,
      height: {max(400, rows_count * 16)},
      sankey: {{ node: {{ label: {{ fontSize: 11 }}, nodePadding: 6 }} }}
    }};

    var chart = new google.visualization.Sankey(document.getElementById('sankey'));
    chart.draw(data, options);
  }}
</script>
</head>
<body>
<h1>{title}</h1>
<div id="sankey"></div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a many-many Sankey diagram to standalone HTML.")
    parser.add_argument("--mapping", required=True, help="Chart mapping JSON (source/target/width)")
    parser.add_argument("--data", required=True, help="Relationship rows JSON array")
    parser.add_argument("--out", required=True, help="Output HTML file")
    args = parser.parse_args()

    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    rows = json.loads(Path(args.data).read_text(encoding="utf-8"))

    html = render(mapping, rows)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
