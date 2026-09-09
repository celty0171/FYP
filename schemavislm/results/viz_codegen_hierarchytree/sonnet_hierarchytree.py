"""Reference hierarchy-tree renderer for one_many_relationship selections (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_hierarchytree.md, strictly per the
McBrien paper / pattern_notes one-many rules. A one-many relationship links a parent entity `Ep`
to a child entity `Ec`; the hierarchy tree shows "instances of parent entity `Ep` ... as nodes
connected by lines to child instances `Ec`. A discrete attribute `a1` may optionally be used to
colour the links between the entities." (pattern_notes). So this is a node-link tree, NOT an
area chart: unlike the tree map / circle packing it does **not** require a scalar measure
(pattern_notes: "Hierarchy tree does not require scalar size, but may use a discrete attribute for
colour"). The optional discrete attribute colours the parent->child **links**, not the nodes.

Mapping (Step-2 shape): { "table": <Ec>, "parent": <kp = FK column>, "child": <kc = child key>,
"color": <optional discrete attribute on Ec> }. Two-level hierarchy root -> parent values ->
child instances; laid out with d3.tree(); links coloured by the child's discrete attribute when
`color` is given, otherwise a neutral grey.

Reads a flat row array or the grouped Mondial database (mapping["table"]). HTML by plain
concatenation (no f-string / str.format). Std-lib only.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

JS_BODY = """
const dx = 12, dy = 210;
const root = d3.hierarchy(data);
d3.tree().nodeSize([dx, dy])(root);

let x0 = Infinity, x1 = -Infinity;
root.each(d => { if (d.x > x1) x1 = d.x; if (d.x < x0) x0 = d.x; });

const margin = {top: 24, right: 180, bottom: 24, left: 110};
const height = (x1 - x0) + margin.top + margin.bottom;
const width = dy * (root.height + 0.4) + margin.left + margin.right;

const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top - x0})`);

// The optional discrete attribute colours the parent->child links (per the paper).
const colorVals = colorName ? Array.from(new Set(root.leaves().map(d => d.data._color).filter(v => v != null))) : [];
const color = d3.scaleOrdinal(colorVals, d3.quantize(d3.interpolateRainbow, Math.max(2, colorVals.length)));
const linkColor = d => (colorName && d.target.data._color != null) ? color(d.target.data._color) : "#bbb";

const link = g.append("g").attr("fill", "none")
  .selectAll("path").data(root.links()).join("path")
  .attr("d", d3.linkHorizontal().x(d => d.y).y(d => d.x))
  .attr("stroke", linkColor)
  .attr("stroke-opacity", 0.55)
  .attr("stroke-width", 1.2);

const node = g.append("g").selectAll("g").data(root.descendants()).join("g")
  .attr("transform", d => `translate(${d.y},${d.x})`);

node.append("circle")
  .attr("r", d => d.depth === 0 ? 0 : (d.children ? 3.5 : 2.4))
  .attr("fill", d => d.children ? "#555" : "#9aa0a6");

node.append("text")
  .attr("dy", "0.31em")
  .attr("x", d => d.children ? -6 : 6)
  .attr("text-anchor", d => d.children ? "end" : "start")
  .style("font-size", d => d.depth === 1 ? "10px" : "8px")
  .text(d => d.depth === 0 ? "" : d.data.name);

const tip = d3.select("#tip");
// Escape values only where they enter innerHTML (the tooltip); on-canvas labels use .text() and stay raw.
const escHtml = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

node
  .on("mouseover", (event, d) => {
    if (d.depth === 0) return;
    const isParent = !!d.children;
    link.attr("stroke-opacity", l => (isParent ? l.source === d : l.target === d) ? 0.95 : 0.05);
    let info;
    if (isParent) {
      info = "<strong>" + escHtml(d.data.name) + "</strong><br>" + parentName + "<br>" + childName + " count: " + d.children.length;
    } else {
      info = "<strong>" + escHtml(d.data.name) + "</strong><br>" + parentName + ": " + escHtml(d.parent.data.name)
           + (colorName && d.data._color != null ? "<br>" + colorName + ": " + escHtml(d.data._color) : "");
    }
    tip.style("opacity", 1).html(info);
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", () => { link.attr("stroke-opacity", 0.55); tip.style("opacity", 0); });

if (colorVals.length) {
  const legend = d3.select("#legend");
  colorVals.forEach(v => {
    const item = legend.append("span").attr("class", "lg");
    item.append("span").attr("class", "sw").style("background", color(v));
    item.append("span").text(v);
  });
}
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
  #legend { margin: 0 0 8px; font-size: 11px; }
  #legend .lg { display: inline-flex; align-items: center; margin: 0 10px 4px 0; }
  #legend .sw { display: inline-block; width: 11px; height: 11px; border-radius: 2px; margin-right: 4px; }
  text { fill: #222; }
  #chart { overflow-x: auto; }
  #tip { position: absolute; opacity: 0; pointer-events: none; background: rgba(0,0,0,0.82);
         color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px; line-height: 1.4; }
</style>
</head>
<body>
<h1>__T__</h1>
<p id="sub">__SUB__</p>
<div id="legend"></div>
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
    p_col, c_col = mapping["parent"], mapping["child"]
    color_col = mapping.get("color")  # optional discrete attribute → colours the links

    # Two-level hierarchy: parent value -> child instances; drop rows with a null parent.
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for r in rows:
        p = r.get(p_col)
        if p is None or p == "":
            continue
        p = str(p)
        if p not in groups:
            groups[p] = []
            order.append(p)
        child: dict[str, Any] = {"name": str(r.get(c_col))}
        if color_col:
            cv = r.get(color_col)
            child["_color"] = None if cv is None or cv == "" else str(cv)
        groups[p].append(child)

    children = [{"name": p, "children": groups[p]} for p in order]
    data = {"name": "root", "children": children}

    n_children = sum(len(v) for v in groups.values())
    title = html.escape(mapping.get("title") or (p_col + " → " + c_col + " hierarchy tree"))
    sub = ("Parent (" + p_col + ") nodes are linked to their " + c_col + " child nodes. "
           + str(len(order)) + " parents, " + str(n_children) + " children.")
    if color_col:
        sub += " Links coloured by " + str(color_col) + "."
    subtitle = html.escape(sub)

    return (
        HEAD.replace("__T__", title).replace("__SUB__", subtitle)
        + "const data = " + json.dumps(data) + ";\n"
        + "const parentName = " + json.dumps(p_col) + ", childName = " + json.dumps(c_col) + ";\n"
        + "const colorName = " + json.dumps(color_col) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a one-many hierarchy tree to standalone HTML (D3 v7).")
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
