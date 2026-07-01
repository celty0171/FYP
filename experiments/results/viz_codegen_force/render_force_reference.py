"""Reference force-directed graph renderer for the two relationship patterns (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_force.md. A force
graph is the **topology** reading of a relationship — it reveals clusters, hubs,
bridges and components that neither the node-link ribbons nor the matrix expose.
It serves **both** relationship patterns and, like the matrix, does not require a
scalar attribute (edge ``"count"`` fallback):

* ``reflexive_many_many_relationship`` — one node set; every node is an instance of
  the same entity type (nodes coloured by degree).
* ``many_many_relationship`` — two node sets (``source`` = group 0, ``target`` =
  group 1); nodes coloured by group so the bipartite structure is visible.

Link weight is a scalar ``value`` column, else the legacy ``width`` column, else the
edge ``"count"`` (parallel edges collapsed, weights summed). The simulation runs in
the browser via ``d3-force``; the layout is seeded deterministically (fixed initial
positions + fixed alpha schedule) so repeated runs are stable. HTML assembled by
plain string concatenation. Std-lib only; D3 v7 + d3-force; hover interaction.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

# Literal JS braces; dynamic values (nodes/links/labels/size/bipartite) concatenated in render().
JS_BODY = """
const width = size, height = size;
const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const tip = d3.select("#tip");
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

const maxW = d3.max(links, l => l.w) || 1;
const wScale = d3.scaleSqrt().domain([0, maxW]).range([0.4, 6]);
const groupColor = ["#1f77b4", "#ff7f0e"];
const degree = new Map(nodes.map(n => [n.id, 0]));
links.forEach(l => { degree.set(l.source, degree.get(l.source) + 1); degree.set(l.target, degree.get(l.target) + 1); });
const maxDeg = d3.max(nodes, n => degree.get(n.id)) || 1;
const degColor = d3.scaleSequential(d3.interpolateViridis).domain([0, maxDeg]);
const nodeFill = n => bipartite ? groupColor[n.group] : degColor(degree.get(n.id));
// Node radius on a sqrt of degree, clamped so hubs stand out yet singletons stay visible.
const nodeR = n => Math.max(3, Math.min(14, 3 + 2 * Math.sqrt(degree.get(n.id))));

// Deterministic seed: place nodes on a circle before the simulation so the layout is reproducible.
nodes.forEach((n, i) => {
  const a = 2 * Math.PI * i / nodes.length;
  n.x = width / 2 + Math.min(width, height) / 3 * Math.cos(a);
  n.y = height / 2 + Math.min(width, height) / 3 * Math.sin(a);
});

const sim = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(links).id(d => d.id).distance(40).strength(l => 0.2 + 0.6 * wScale(l.w) / 6))
  .force("charge", d3.forceManyBody().strength(-30))
  .force("center", d3.forceCenter(width / 2, height / 2))
  .force("collide", d3.forceCollide(d => nodeR(d) + 1.5))
  .stop();
// Run the simulation to a fixed number of ticks (no animation randomness across runs).
for (let i = 0; i < 300; i++) sim.tick();

const adj = new Map(nodes.map(n => [n.id, new Set()]));
links.forEach(l => { adj.get(l.source.id).add(l.target.id); adj.get(l.target.id).add(l.source.id); });

const link = svg.append("g").attr("stroke", "#999").attr("stroke-opacity", 0.5)
  .selectAll("line").data(links).join("line")
  .attr("stroke-width", d => wScale(d.w))
  .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
  .attr("x2", d => d.target.x).attr("y2", d => d.target.y);

const node = svg.append("g").attr("stroke", "#fff").attr("stroke-width", 1)
  .selectAll("circle").data(nodes).join("circle")
  .attr("r", d => nodeR(d))
  .attr("cx", d => d.x).attr("cy", d => d.y)
  .attr("fill", nodeFill)
  .on("mouseover", (event, d) => {
    const nb = adj.get(d.id);
    node.attr("opacity", o => (o.id === d.id || nb.has(o.id)) ? 1 : 0.15);
    link.attr("stroke-opacity", l => (l.source.id === d.id || l.target.id === d.id) ? 0.9 : 0.05);
    tip.style("opacity", 1).html("<strong>" + d.id + "</strong><br>degree: " + degree.get(d.id));
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", () => { node.attr("opacity", 1); link.attr("stroke-opacity", 0.5); tip.style("opacity", 0); });

link.on("mouseover", (event, d) => {
  tip.style("opacity", 1).html(d.source.id + " &harr; " + d.target.id + "<br>" + valueLabel + ": "
    + (Number.isInteger(d.w) ? d.w : d.w.toFixed(2)));
  moveTip(event);
}).on("mousemove", moveTip).on("mouseout", () => tip.style("opacity", 0));

// Persistently label only the salient hubs (top by degree); everything else is on hover,
// so a dense graph does not become an unreadable smear. A white halo keeps text legible.
const hubs = nodes.slice().sort((a, b) => degree.get(b.id) - degree.get(a.id)).slice(0, Math.min(12, nodes.length));
svg.append("g").attr("pointer-events", "none")
  .selectAll("text").data(hubs).join("text")
  .attr("x", d => d.x).attr("y", d => d.y - (nodeR(d) + 3))
  .attr("text-anchor", "middle").attr("font-size", 10).attr("fill", "#222")
  .attr("stroke", "#fff").attr("stroke-width", 3).attr("paint-order", "stroke")
  .text(d => d.id);

if (bipartite && legend.length === 2) {
  const lg = svg.append("g").attr("transform", "translate(16,16)");
  legend.forEach((lab, i) => {
    const row = lg.append("g").attr("transform", "translate(0," + (i * 18) + ")");
    row.append("circle").attr("r", 6).attr("cx", 6).attr("cy", 6).attr("fill", groupColor[i]);
    row.append("text").attr("x", 18).attr("y", 10).attr("font-size", 11).text(lab);
  });
}

// Fit the SVG viewport to all rendered content so nothing is ever clipped, whatever the
// data: the force simulation can push nodes past the initial box. getBBox() returns the
// tight box of every mark; resize the root <svg> to match.
{
  const rootSvg = d3.select("#chart").select("svg");
  const bb = rootSvg.node().getBBox();
  const pad = 16;
  rootSvg.attr("viewBox", [bb.x - pad, bb.y - pad, bb.width + 2 * pad, bb.height + 2 * pad].join(" "))
         .attr("width", bb.width + 2 * pad)
         .attr("height", bb.height + 2 * pad);
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
  text { fill: #222; }
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
    """Accept either a flat row array, or the grouped Mondial DB and select the table."""
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


def _encoding(mapping: dict[str, Any]) -> dict[str, Any]:
    """Resolve source/target and the optional weight column (value → width → count)."""
    src = mapping.get("source")
    tgt = mapping.get("target")
    if not (src and tgt):
        sub = mapping.get("chart_mapping")
        if isinstance(sub, dict):
            src, tgt = sub.get("source"), sub.get("target")
            mapping = {**mapping, **sub}
    if not (src and tgt):
        sel = mapping.get("selected_visualisation", {})
        enc = sel.get("encoding") if isinstance(sel, dict) else None
        if isinstance(enc, dict):
            src, tgt = enc.get("source"), enc.get("target")
            mapping = {**mapping, **enc}
    if not (src and tgt):
        raise ValueError("mapping must provide source/target")
    value = mapping.get("value")
    if value is None:
        value = mapping.get("width")
    use_count = value is None or str(value).lower() == "count"
    return {"source": src, "target": tgt, "value": None if use_count else value}


def render(mapping: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    enc = _encoding(mapping)
    s_col, t_col, v_col = enc["source"], enc["target"], enc["value"]

    src_vals = sorted({str(r[s_col]) for r in rows if s_col in r})
    tgt_vals = sorted({str(r[t_col]) for r in rows if t_col in r})

    pattern = str(mapping.get("pattern", "")).lower()
    if "reflexive" in pattern:
        bipartite = False
    elif "many_many" in pattern:
        bipartite = True
    else:
        bipartite = len(set(src_vals) & set(tgt_vals)) == 0 and bool(src_vals) and bool(tgt_vals)

    # Namespace nodes for the bipartite case so an E1 and an E2 with the same string
    # are distinct nodes; keep the display label clean.
    def node_id(prefix: str, name: str) -> str:
        return (prefix + name) if bipartite else name

    node_ids: list[str] = []
    node_group: dict[str, int] = {}
    node_label: dict[str, str] = {}
    if bipartite:
        for v in src_vals:
            nid = node_id("s::", v)
            node_ids.append(nid); node_group[nid] = 0; node_label[nid] = v
        for v in tgt_vals:
            nid = node_id("t::", v)
            node_ids.append(nid); node_group[nid] = 1; node_label[nid] = v
    else:
        for v in sorted(set(src_vals) | set(tgt_vals)):
            node_ids.append(v); node_group[v] = 0; node_label[v] = v

    weights: dict[tuple[str, str], float] = {}
    for r in rows:
        if s_col not in r or t_col not in r:
            continue
        a = node_id("s::", str(r[s_col]))
        b = node_id("t::", str(r[t_col]))
        if v_col is None:
            w = 1.0
        else:
            try:
                w = float(r[v_col])
            except (TypeError, ValueError):
                continue
        key = (a, b) if bipartite else tuple(sorted((a, b)))
        weights[key] = weights.get(key, 0.0) + w

    nodes = [{"id": html.escape(node_label[nid]), "group": node_group[nid]} for nid in node_ids]
    esc = {nid: html.escape(node_label[nid]) for nid in node_ids}
    links = [{"source": esc[a], "target": esc[b], "w": w} for (a, b), w in weights.items()]

    value_label = "count" if v_col is None else v_col
    default_title = s_col + " – " + t_col + " force-directed graph"
    title = html.escape(mapping.get("title") or default_title)
    if bipartite:
        subtitle = "Node-link topology. Bipartite: '" + s_col + "' (blue) and '" + t_col + "' (orange); link width encodes '" + value_label + "'."
        legend = [s_col, t_col]
    else:
        subtitle = "Node-link topology of one entity set; node colour encodes degree, link width encodes '" + value_label + "'."
        legend = []
    n = len(nodes)
    size = max(640, min(1200, int(n ** 0.5) * 60 + 300))

    return (
        HEAD.replace("__T__", title).replace("__SUB__", html.escape(subtitle))
        + "const nodes = " + json.dumps(nodes) + ";\n"
        + "const links = " + json.dumps(links) + ";\n"
        + "const valueLabel = " + json.dumps(html.escape(value_label)) + ";\n"
        + "const bipartite = " + ("true" if bipartite else "false") + ";\n"
        + "const legend = " + json.dumps([html.escape(x) for x in legend]) + ";\n"
        + "const size = " + str(size) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a many-many / reflexive force-directed graph to standalone HTML (D3 v7 + d3-force).")
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
