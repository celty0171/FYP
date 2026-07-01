"""Reference spider/radar renderer for weak_entity selections (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_spider.md. One polygon
per parent key (ring), one axis per child key (spoke), radius = scalar measure. Because
a radar is unreadable with many rings/spokes, keeps the top max_rings rings by total and
the top max_spokes spokes by frequency, padding missing combinations with 0. Reads a flat
row array or the grouped Mondial database (mapping["table"]). HTML by plain concatenation.
Std-lib only.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

JS_BODY = """
const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const cx = width / 2, cy = height / 2 + 6, R = Math.min(width, height) / 2 - 90;
const g = svg.append("g").attr("transform", `translate(${cx},${cy})`);

const n = spokes.length;
const angle = i => (i / n) * 2 * Math.PI - Math.PI / 2;
const r = d3.scaleLinear().domain([0, maxVal || 1]).range([0, R]);
const color = d3.scaleOrdinal(rings.map(d => d.name), d3.schemeCategory10);

// grid rings + spoke axes + labels
const levels = 4;
for (let l = 1; l <= levels; l++) {
  g.append("circle").attr("r", R * l / levels).attr("fill", "none").attr("stroke", "#e3e3e3");
}
spokes.forEach((sp, i) => {
  const a = angle(i), px = Math.cos(a) * R, py = Math.sin(a) * R;
  g.append("line").attr("x1", 0).attr("y1", 0).attr("x2", px).attr("y2", py).attr("stroke", "#ddd");
  g.append("text").attr("x", Math.cos(a) * (R + 10)).attr("y", Math.sin(a) * (R + 10))
    .attr("text-anchor", Math.abs(a + Math.PI / 2) < 0.01 || Math.abs(a - Math.PI / 2) < 0.01 ? "middle" : (Math.cos(a) > 0 ? "start" : "end"))
    .attr("dy", "0.32em").attr("font-size", "9px").text(sp);
});

const tip = d3.select("#tip");
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

function polygon(values) {
  return values.map((v, i) => {
    const a = angle(i), rad = r(v || 0);
    return [Math.cos(a) * rad, Math.sin(a) * rad];
  });
}
const lineGen = d3.line().x(d => d[0]).y(d => d[1]).curve(d3.curveLinearClosed);

const poly = g.append("g").selectAll("path").data(rings).join("path")
  .attr("d", d => lineGen(polygon(d.values)))
  .attr("fill", d => color(d.name))
  .attr("fill-opacity", 0.12)
  .attr("stroke", d => color(d.name))
  .attr("stroke-width", 1.6);

poly
  .on("mouseover", (event, d) => {
    poly.attr("fill-opacity", p => p === d ? 0.35 : 0.03).attr("stroke-opacity", p => p === d ? 1 : 0.12);
    d3.select(event.currentTarget).raise();
    tip.style("opacity", 1).html("<strong>" + ringName + ": " + d.name + "</strong>");
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", () => { poly.attr("fill-opacity", 0.12).attr("stroke-opacity", 1); tip.style("opacity", 0); });
"""

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__T__</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  body { font-family: Arial, sans-serif; margin: 16px; }
  h1 { font-size: 18px; margin-bottom: 2px; }
  #sub { color: #555; font-size: 12px; margin: 0 0 8px; }
  #tip { position: absolute; opacity: 0; pointer-events: none; background: rgba(0,0,0,0.82);
         color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px; line-height: 1.4; }
</style>
</head>
<body>
<h1>__T__</h1>
<p id="sub">__SUB__</p>
<div id="chart"></div>
<div id="tip"></div>
<script>
"""


def _rows_for(mapping: dict[str, Any], data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        table = mapping.get("table")
        if isinstance(data.get("tables"), dict):
            if not table:
                raise ValueError("data is a grouped database; mapping must name the relation via 'table'")
            return data["tables"][table]
        if table in data:
            return data[table]
    raise ValueError("unsupported data shape: expected a row array or a grouped {'tables': {...}} database")


def render(mapping: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    ring_col, spoke_col, v_col = mapping["ring"], mapping["spoke"], mapping["value"]
    max_rings = int(mapping.get("max_rings", 8))
    max_spokes = int(mapping.get("max_spokes", 12))

    cell: dict[tuple[str, str], float] = {}
    ring_total: dict[str, float] = {}
    spoke_freq: dict[str, int] = {}
    for r in rows:
        try:
            v = float(r[v_col])
        except (TypeError, ValueError, KeyError):
            continue
        rv, sv = str(r.get(ring_col)), str(r.get(spoke_col))
        cell[(rv, sv)] = cell.get((rv, sv), 0.0) + v
        ring_total[rv] = ring_total.get(rv, 0.0) + v

    top_rings = sorted(ring_total, key=lambda k: ring_total[k], reverse=True)[:max_rings]
    for (rv, sv), val in cell.items():
        if rv in top_rings:
            spoke_freq[sv] = spoke_freq.get(sv, 0) + 1
    top_spokes = sorted(spoke_freq, key=lambda k: (spoke_freq[k], k), reverse=True)[:max_spokes]
    top_spokes = sorted(top_spokes)  # stable display order

    rings = [{"name": html.escape(rv), "values": [cell.get((rv, sv), 0.0) for sv in top_spokes]} for rv in top_rings]
    spokes = [html.escape(s) for s in top_spokes]
    max_val = max((v for rg in rings for v in rg["values"]), default=1.0)

    n_rings_all = len(ring_total)
    n_spokes_all = len(spoke_freq) if spoke_freq else len({s for (_, s) in cell})
    title = html.escape(mapping.get("title") or (v_col + " by " + spoke_col + " across " + ring_col + " (spider chart)"))
    cap_note = ""
    if n_rings_all > len(top_rings) or n_spokes_all > len(top_spokes):
        cap_note = " (capped from " + str(n_rings_all) + " " + ring_col + " / " + str(n_spokes_all) + " " + spoke_col + " for readability)"
    subtitle = html.escape("Rings = " + ring_col + " (top " + str(len(top_rings)) + " by total " + v_col
                           + "), spokes = " + spoke_col + cap_note + ".")
    width, height = 760, 720

    return (
        HEAD.replace("__T__", title).replace("__SUB__", subtitle)
        + "const rings = " + json.dumps(rings) + ";\n"
        + "const spokes = " + json.dumps(spokes) + ";\n"
        + "const maxVal = " + json.dumps(max_val) + ";\n"
        + "const ringName = " + json.dumps(ring_col) + ";\n"
        + "const width = " + str(width) + ", height = " + str(height) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a weak-entity spider/radar chart to standalone HTML (D3 v7).")
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    rows = _rows_for(mapping, json.loads(Path(args.data).read_text(encoding="utf-8")))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(mapping, rows), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
