"""Reference tree-map renderer for one_many_relationship selections (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_treemap.md. Reads a
chart mapping and the child rows at run time (a flat array, or the grouped Mondial
database selected by mapping["table"]) and emits a complete, standalone D3 v7
tree-map HTML file with hover interaction. Builds a two-level parent -> child
hierarchy; leaf area = measure. HTML assembled by plain concatenation (no f-string
/ str.format). Std-lib only.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

JS_BODY = """
const margin = {top: 20, right: 10, bottom: 10, left: 10};
const innerW = width - margin.left - margin.right;
const innerH = height - margin.top - margin.bottom;

const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

const root = d3.hierarchy(data).sum(d => d.value || 0).sort((a, b) => b.value - a.value);
d3.treemap().size([innerW, innerH]).paddingInner(1).paddingTop(14).round(true)(root);

const parents = root.children || [];
const color = d3.scaleOrdinal(parents.map(d => d.data.name), d3.quantize(d3.interpolateRainbow, Math.max(2, parents.length)));
// Optional colour by a leaf attribute (paper Section-3): scalar -> spectrum, discrete -> key;
// otherwise the default is to colour each child by its parent.
const colorScalar = colorName && colorType === "scalar";
const leafColorVals = colorName ? root.leaves().map(d => d.data.color) : [];
const colorSeq = colorScalar ? d3.scaleSequential(d3.interpolateViridis).domain(d3.extent(leafColorVals, v => +v)) : null;
const colorOrd = (colorName && !colorScalar) ? d3.scaleOrdinal(Array.from(new Set(leafColorVals)), d3.schemeCategory10) : null;
const leafFill = d => colorName ? (colorScalar ? colorSeq(+d.data.color) : colorOrd(d.data.color)) : color(d.parent.data.name);
const tip = d3.select("#tip");
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

const leaf = g.selectAll("g.leaf").data(root.leaves()).join("g")
  .attr("class", "leaf")
  .attr("transform", d => `translate(${d.x0},${d.y0})`);

leaf.append("rect")
  .attr("width", d => Math.max(0, d.x1 - d.x0))
  .attr("height", d => Math.max(0, d.y1 - d.y0))
  .attr("fill", d => leafFill(d))
  .attr("fill-opacity", 0.85)
  .attr("stroke", "#fff");

leaf.append("text")
  .attr("x", 3).attr("y", 11)
  .text(d => (d.x1 - d.x0 > 28 && d.y1 - d.y0 > 13) ? d.data.name : "");

// Parent-group labels.
g.append("g").selectAll("text.group").data(parents).join("text")
  .attr("class", "group")
  .attr("x", d => d.x0 + 3).attr("y", d => d.y0 + 11)
  .attr("font-weight", "bold").attr("font-size", "10px")
  .text(d => (d.x1 - d.x0 > 44) ? d.data.name : "");

leaf
  .on("mouseover", (event, d) => {
    leaf.select("rect").attr("fill-opacity", x => x.parent === d.parent ? 0.95 : 0.18);
    tip.style("opacity", 1).html("<strong>" + d.data.name + "</strong><br>" + parentName + ": " + d.parent.data.name + "<br>" + measureName + ": " + d.value);
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", () => { leaf.select("rect").attr("fill-opacity", 0.85); tip.style("opacity", 0); });
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
  text { font-size: 9px; }
  .group { fill: #222; }
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
    if {"parent", "child", "measure"} <= set(mapping):
        return {k: mapping[k] for k in ("parent", "child", "measure")}
    sub = mapping.get("chart_mapping")
    if isinstance(sub, dict):
        tm = sub.get("tree map", sub)
        if isinstance(tm, dict) and {"parent_key", "child_key", "measure"} <= set(tm):
            return {"parent": tm["parent_key"], "child": tm["child_key"], "measure": tm["measure"]}
    raise ValueError("mapping must provide parent/child/measure")


def render(mapping: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    enc = _encoding(mapping)
    p_col, c_col, m_col = enc["parent"], enc["child"], enc["measure"]
    color_col = mapping.get("color")  # paper: optional a2 colour of the child rectangles

    # Two-level hierarchy: parent -> children; drop rows with a null parent or non-numeric measure.
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for r in rows:
        p = r.get(p_col)
        if p is None or p == "":
            continue
        try:
            v = float(r.get(m_col))
        except (TypeError, ValueError):
            continue
        v = max(0.0, v)
        p = str(p)
        if p not in groups:
            groups[p] = []
            order.append(p)
        leaf = {"name": html.escape(str(r.get(c_col))), "value": v}
        if color_col is not None:
            leaf["color"] = html.escape(str(r.get(color_col)))
        groups[p].append(leaf)

    children = [{"name": html.escape(p), "children": groups[p]} for p in order]
    data = {"name": "root", "children": children}

    n_children = sum(len(v) for v in groups.values())
    title = html.escape(mapping.get("title") or (p_col + " → " + c_col + " tree map"))
    subtitle = html.escape("Each parent (" + p_col + ") is subdivided into its " + c_col
                           + " children; rectangle area = " + m_col + ". "
                           + str(len(order)) + " parents, " + str(n_children) + " children.")
    width = 1000
    height = 720

    return (
        HEAD.replace("__T__", title).replace("__SUB__", subtitle)
        + "const data = " + json.dumps(data) + ";\n"
        + "const parentName = " + json.dumps(p_col) + ", measureName = " + json.dumps(m_col) + ";\n"
        + "const colorName = " + json.dumps(color_col) + ", colorType = " + json.dumps(mapping.get("color_type")) + ";\n"
        + "const width = " + str(width) + ", height = " + str(height) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a one-many tree map to standalone HTML (D3 v7).")
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
