"""Reference scatter / bubble renderer for basic_entity selections (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_scatter.md / chart_bubble.md.
Scatter and bubble share one cartesian data-prep recipe, so one renderer serves both:
when the mapping carries a `size` field it draws a bubble chart (area = size via
scaleSqrt); otherwise a scatter diagram. Reads a flat row array or the grouped Mondial
database (mapping["table"]). HTML assembled by plain concatenation (no f-string /
str.format). Std-lib only.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

JS_BODY = """
const margin = {top: 24, right: 30, bottom: 52, left: 64};
const innerW = width - margin.left - margin.right;
const innerH = height - margin.top - margin.bottom;

const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

const x = d3.scaleLinear().domain(d3.extent(data, d => d.x)).nice().range([0, innerW]);
const y = d3.scaleLinear().domain(d3.extent(data, d => d.y)).nice().range([innerH, 0]);
const rScale = sizeName ? d3.scaleSqrt().domain([0, d3.max(data, d => d.size) || 1]).range([3, 22]) : null;
// Colour per the paper's Section-3 rule: scalar -> spectrum, discrete -> ordinal key.
const colorScalar = colorName && colorType === "scalar";
const colorVals = (colorName && !colorScalar) ? Array.from(new Set(data.map(d => d.color))) : [];
const colorSeq = colorScalar ? d3.scaleSequential(d3.interpolateViridis).domain(d3.extent(data, d => +d.color)) : null;
const colorOrd = (colorName && !colorScalar) ? d3.scaleOrdinal(colorVals, d3.schemeCategory10) : null;
const colorOf = d => colorScalar ? colorSeq(+d.color) : (colorOrd ? colorOrd(d.color) : "#4a78b5");

g.append("g").attr("transform", `translate(0,${innerH})`).call(d3.axisBottom(x).ticks(8));
g.append("g").call(d3.axisLeft(y).ticks(8));
g.append("text").attr("x", innerW / 2).attr("y", innerH + 40).attr("text-anchor", "middle").attr("font-size", "11px").text(xName);
g.append("text").attr("transform", "rotate(-90)").attr("x", -innerH / 2).attr("y", -48).attr("text-anchor", "middle").attr("font-size", "11px").text(yName);

const tip = d3.select("#tip");
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

// Draw larger bubbles first so small ones are not hidden.
const drawData = rScale ? data.slice().sort((a, b) => b.size - a.size) : data;
const dot = g.append("g").selectAll("circle").data(drawData).join("circle")
  .attr("cx", d => x(d.x))
  .attr("cy", d => y(d.y))
  .attr("r", d => rScale ? rScale(d.size) : 4)
  .attr("fill", d => colorName ? colorOf(d) : "#4a78b5")
  .attr("fill-opacity", 0.7)
  .attr("stroke", "#fff");

dot
  .on("mouseover", (event, d) => {
    dot.attr("fill-opacity", p => p === d ? 1 : 0.12);
    let v = "<strong>" + d.label + "</strong><br>" + xName + ": " + d.x + "<br>" + yName + ": " + d.y;
    if (sizeName) v += "<br>" + sizeName + ": " + d.size;
    if (colorName) v += "<br>" + colorName + ": " + d.color;
    tip.style("opacity", 1).html(v);
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", () => { dot.attr("fill-opacity", 0.7); tip.style("opacity", 0); });
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
    x_col, y_col = mapping["x"], mapping["y"]
    key_col = mapping.get("key")
    size_col = mapping.get("size")
    color_col = mapping.get("color")

    points: list[dict[str, Any]] = []
    for r in rows:
        try:
            xv, yv = float(r[x_col]), float(r[y_col])
        except (TypeError, ValueError, KeyError):
            continue
        p: dict[str, Any] = {
            "label": html.escape(str(r.get(key_col))) if key_col else "",
            "x": xv, "y": yv,
        }
        if size_col is not None:
            try:
                p["size"] = max(0.0, float(r[size_col]))
            except (TypeError, ValueError, KeyError):
                continue
        if color_col is not None:
            p["color"] = html.escape(str(r.get(color_col)))
        points.append(p)

    is_bubble = size_col is not None
    chart = "bubble chart" if is_bubble else "scatter diagram"
    default_title = y_col + " vs " + x_col + (" (size = " + str(size_col) + ")" if is_bubble else "") + " — " + chart
    title = html.escape(mapping.get("title") or default_title)
    sub = "One point per " + (str(key_col) if key_col else "row") + ": x = " + x_col + ", y = " + y_col
    if is_bubble:
        sub += ", area = " + str(size_col)
    if color_col:
        sub += ", colour = " + str(color_col)
    sub += ". " + str(len(points)) + " instances."
    subtitle = html.escape(sub)
    width = 920
    height = 640

    return (
        HEAD.replace("__T__", title).replace("__SUB__", subtitle)
        + "const data = " + json.dumps(points) + ";\n"
        + "const xName = " + json.dumps(x_col) + ", yName = " + json.dumps(y_col) + ";\n"
        + "const sizeName = " + json.dumps(size_col) + ", colorName = " + json.dumps(color_col)
        + ", colorType = " + json.dumps(mapping.get("color_type")) + ";\n"
        + "const width = " + str(width) + ", height = " + str(height) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a basic-entity scatter/bubble chart to standalone HTML (D3 v7).")
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    rows = _rows_for(mapping, json.loads(Path(args.data).read_text(encoding="utf-8")))
    html_doc = render(mapping, rows)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {out} ({len(html_doc)} bytes)")


if __name__ == "__main__":
    main()
