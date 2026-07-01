"""Reference bar-chart renderer for basic_entity selections (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_bar.md. Reads a chart
mapping and the entity rows at run time (a flat array, or the grouped Mondial
database selected by mapping["table"]) and emits a complete, standalone D3 v7
horizontal bar chart with hover interaction. One bar per entity instance; bar
length = measure. HTML assembled by plain concatenation (no f-string / str.format).
Std-lib only.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

JS_BODY = """
const margin = {top: 24, right: 90, bottom: 10, left: 170};
const innerW = width - margin.left - margin.right;
const innerH = height - margin.top - margin.bottom;

const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

const y = d3.scaleBand().domain(data.map(d => d.label)).range([0, innerH]).padding(0.15);
const x = d3.scaleLinear().domain([0, d3.max(data, d => d.value) || 1]).range([0, innerW]).nice();

g.append("g").call(d3.axisTop(x).ticks(6));
g.append("g").call(d3.axisLeft(y)).selectAll("text").style("font-size", "8px");

const tip = d3.select("#tip");
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

const bar = g.append("g").selectAll("rect").data(data).join("rect")
  .attr("x", 0)
  .attr("y", d => y(d.label))
  .attr("height", y.bandwidth())
  .attr("width", d => x(d.value))
  .attr("fill", "#4a78b5")
  .attr("fill-opacity", 0.9);

// Value labels at the bar ends when the bar is tall enough to fit text.
g.append("g").selectAll("text.val").data(data).join("text")
  .attr("class", "val")
  .attr("x", d => x(d.value) + 4)
  .attr("y", d => y(d.label) + y.bandwidth() / 2)
  .attr("dy", "0.35em")
  .style("font-size", "8px")
  .text(d => y.bandwidth() >= 8 ? d.value.toLocaleString() : "");

bar
  .on("mouseover", (event, d) => {
    bar.attr("fill-opacity", b => b === d ? 1 : 0.2);
    tip.style("opacity", 1).html("<strong>" + d.label + "</strong><br>" + measureName + ": " + d.value.toLocaleString());
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", () => { bar.attr("fill-opacity", 0.9); tip.style("opacity", 0); });
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


def _encoding(mapping: dict[str, Any]) -> dict[str, str]:
    if {"key", "measure"} <= set(mapping):
        return {"key": mapping["key"], "measure": mapping["measure"]}
    sub = mapping.get("chart_mapping")
    if isinstance(sub, dict):
        bc = sub.get("bar chart", sub)
        if isinstance(bc, dict) and {"x", "y"} <= set(bc):
            return {"key": bc["x"], "measure": bc["y"]}
    raise ValueError("mapping must provide key/measure")


def render(mapping: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    enc = _encoding(mapping)
    k_col, m_col = enc["key"], enc["measure"]

    # One bar per instance; drop non-numeric measures; sort by measure descending.
    bars: list[dict[str, Any]] = []
    for r in rows:
        if k_col not in r or m_col not in r:
            continue
        try:
            v = float(r[m_col])
        except (TypeError, ValueError):
            continue
        bars.append({"label": html.escape(str(r[k_col])), "value": v})
    bars.sort(key=lambda d: d["value"], reverse=True)

    title = html.escape(mapping.get("title") or (m_col + " by " + k_col + " (bar chart)"))
    subtitle = html.escape("One bar per " + k_col + "; bar length = " + m_col + ", sorted descending. "
                           + str(len(bars)) + " instances.")
    width = 960
    height = max(360, len(bars) * 14 + 60)

    return (
        HEAD.replace("__T__", title).replace("__SUB__", subtitle)
        + "const data = " + json.dumps(bars) + ";\n"
        + "const keyName = " + json.dumps(k_col) + ", measureName = " + json.dumps(m_col) + ";\n"
        + "const width = " + str(width) + ", height = " + str(height) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a basic-entity bar chart to standalone HTML (D3 v7).")
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
