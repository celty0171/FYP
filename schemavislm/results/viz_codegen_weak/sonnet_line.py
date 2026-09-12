from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

JS_BODY = """
const margin = {top: 24, right: 30, bottom: 50, left: 70};
const innerW = width - margin.left - margin.right;
const innerH = height - margin.top - margin.bottom;

const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

const allX = data.flatMap(s => s.pts.map(p => p[0]));
const allY = data.flatMap(s => s.pts.map(p => p[1]));
const x = d3.scaleLinear().domain(d3.extent(allX)).nice().range([0, innerW]);
const y = d3.scaleLinear().domain(d3.extent(allY)).nice().range([innerH, 0]);
const color = d3.scaleOrdinal(data.map(s => s.name), d3.schemeCategory10);
const line = d3.line().x(d => x(d[0])).y(d => y(d[1]));

g.append("g").attr("transform", `translate(0,${innerH})`).call(d3.axisBottom(x).ticks(8));
g.append("g").call(d3.axisLeft(y).ticks(8));
g.append("text").attr("x", innerW / 2).attr("y", innerH + 40).attr("text-anchor", "middle").attr("font-size", "11px").text(xName);
g.append("text").attr("transform", "rotate(-90)").attr("x", -innerH / 2).attr("y", -54).attr("text-anchor", "middle").attr("font-size", "11px").text(yName);

const tip = d3.select("#tip");
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

const path = g.append("g").attr("fill", "none").selectAll("path").data(data).join("path")
  .attr("d", s => line(s.pts))
  .attr("stroke", s => color(s.name))
  .attr("stroke-width", 1.2)
  .attr("stroke-opacity", 0.35);

path
  .on("mouseover", (event, d) => {
    path.attr("stroke-opacity", s => s === d ? 1 : 0.05);
    d3.select(event.currentTarget).raise().attr("stroke-width", 2.4);
    tip.style("opacity", 1).html("<strong>" + seriesName + ": " + d.name + "</strong><br>" + d.pts.length + " points");
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", (event) => { path.attr("stroke-opacity", 0.35).attr("stroke-width", 1.2); tip.style("opacity", 0); });
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
  .domain, .tick line { stroke: #ccc; }
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
    s_col, x_col, y_col = mapping["series"], mapping["x"], mapping["y"]

    series: dict[str, list[list[float]]] = {}
    order: list[str] = []
    for r in rows:
        try:
            xv, yv = float(r[x_col]), float(r[y_col])
        except (TypeError, ValueError, KeyError):
            continue
        name = str(r.get(s_col))
        if name not in series:
            series[name] = []
            order.append(name)
        series[name].append([xv, yv])

    data = [{"name": html.escape(n), "pts": sorted(series[n], key=lambda p: p[0])} for n in order]

    title = html.escape(mapping.get("title") or (y_col + " vs " + x_col + " by " + s_col + " (line chart)"))
    subtitle = html.escape("One line per " + s_col + "; x = " + x_col + ", y = " + y_col
                           + ". " + str(len(data)) + " series. Hover a line to trace one.")
    width, height = 980, 620

    return (
        HEAD.replace("__T__", title).replace("__SUB__", subtitle)
        + "const data = " + json.dumps(data) + ";\n"
        + "const seriesName = " + json.dumps(s_col) + ", xName = " + json.dumps(x_col) + ", yName = " + json.dumps(y_col) + ";\n"
        + "const width = " + str(width) + ", height = " + str(height) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a weak-entity line chart to standalone HTML (D3 v7).")
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
