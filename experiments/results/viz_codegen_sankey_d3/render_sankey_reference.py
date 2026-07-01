"""Reference Sankey renderer for the two relationship patterns (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_sankey.md. A Sankey
serves **both** ``many_many_relationship`` and ``reflexive_many_many_relationship``:
the source side (left) and target side (right) are kept as separate namespaced node
identities (``src:`` / ``tgt:``), so the same renderer is correct for both. For
``many_many`` the two columns are different entity sets; for ``reflexive`` they are
the same set drawn as a directed flow, so an instance may legitimately appear on
both sides (as its "as source" and "as target" roles) without the nodes merging.
The pattern is read from ``mapping["pattern"]`` when present, else inferred from the
data (overlapping source/target value sets ⇒ reflexive); it only phrases the
subtitle. Includes the overlap-reduction layout: a deterministic Step A–C ordering
(target affinity seriation, source weighted barycentre, consistent link order)
attached to nodes and fed to d3-sankey via nodeSort / linkSort. Reads a flat row
array or the grouped Mondial database (mapping["table"]). HTML assembled by plain
concatenation (no f-string / str.format). Std-lib only.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

JS_BODY = """
const margin = {top: 20, right: 180, bottom: 20, left: 180};
const innerW = width - margin.left - margin.right;
const innerH = height - margin.top - margin.bottom;

const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

const sankey = d3.sankey()
  .nodeId(d => d.name)
  .nodeWidth(16)
  .nodePadding(8)
  .nodeAlign(d3.sankeyLeft)
  .nodeSort((a, b) => d3.ascending(a.order, b.order))
  .linkSort((a, b) => (a.target.order - b.target.order) || (a.source.order - b.source.order))
  .iterations(32)
  .extent([[0, 0], [innerW, innerH]]);

const graph = sankey({
  nodes: nodes.map(d => Object.assign({}, d)),
  links: links.map(d => Object.assign({}, d))
});

// Colour links by target group so overlapping links stay distinguishable.
const targetLabels = Array.from(new Set(graph.nodes.filter(n => n.name.startsWith("tgt:")).map(n => n.label)));
const color = d3.scaleOrdinal(targetLabels, d3.schemeCategory10);
const tip = d3.select("#tip");
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

// Draw thin minor links last (on top) so they are not buried under thick bundles.
const drawOrder = graph.links.slice().sort((a, b) => b.width - a.width);
const link = g.append("g").attr("fill", "none").selectAll("path").data(drawOrder).join("path")
  .attr("d", d3.sankeyLinkHorizontal())
  .attr("stroke", d => color(d.target.label))
  .attr("stroke-opacity", 0.45)
  .attr("stroke-width", d => Math.max(1, d.width));

const node = g.append("g").selectAll("rect").data(graph.nodes).join("rect")
  .attr("x", d => d.x0)
  .attr("y", d => d.y0)
  .attr("height", d => Math.max(1, d.y1 - d.y0))
  .attr("width", d => d.x1 - d.x0)
  .attr("fill", d => d.name.startsWith("tgt:") ? color(d.label) : "#888")
  .attr("stroke", "#fff");

g.append("g").selectAll("text").data(graph.nodes).join("text")
  .attr("x", d => d.x0 < innerW / 2 ? d.x1 + 4 : d.x0 - 4)
  .attr("y", d => (d.y0 + d.y1) / 2)
  .attr("dy", "0.35em")
  .attr("text-anchor", d => d.x0 < innerW / 2 ? "start" : "end")
  .text(d => d.label);

node
  .on("mouseover", (event, d) => {
    link.attr("stroke-opacity", l => (l.source === d || l.target === d) ? 0.8 : 0.04);
    tip.style("opacity", 1).html("<strong>" + d.label + "</strong><br>total: " + Math.round(d.value));
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", () => { link.attr("stroke-opacity", 0.45); tip.style("opacity", 0); });

link
  .on("mouseover", (event, d) => {
    link.attr("stroke-opacity", l => (l === d) ? 0.9 : 0.04);
    tip.style("opacity", 1).html(d.source.label + " &rarr; " + d.target.label + "<br>" + Math.round(d.value));
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", () => { link.attr("stroke-opacity", 0.45); tip.style("opacity", 0); });
"""

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__T__</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12/dist/d3-sankey.min.js"></script>
<style>
  body { font-family: Arial, sans-serif; margin: 16px; }
  h1 { font-size: 18px; margin-bottom: 2px; }
  #sub { color: #555; font-size: 12px; margin: 0 0 8px; }
  text { font-size: 9px; }
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
    if {"source", "target", "width"} <= set(mapping):
        return {k: mapping[k] for k in ("source", "target", "width")}
    sub = mapping.get("chart_mapping")
    if isinstance(sub, dict) and {"source", "target", "width"} <= set(sub):
        return {k: sub[k] for k in ("source", "target", "width")}
    sel = mapping.get("selected_visualisation", {})
    enc = sel.get("encoding") if isinstance(sel, dict) else None
    if isinstance(enc, dict) and {"source", "target", "width"} <= set(enc):
        return {k: enc[k] for k in ("source", "target", "width")}
    raise ValueError("mapping must provide source/target/width")


def _seriate_targets(targets: list[str], affinity: dict[tuple[str, str], float],
                     incoming: dict[str, float]) -> list[str]:
    """Step A: greedy nearest-neighbour chaining so high-affinity targets are adjacent."""
    remaining = set(targets)
    start = max(remaining, key=lambda t: (incoming[t], t))
    order = [start]
    remaining.discard(start)
    while remaining:
        last = order[-1]
        nxt = max(remaining, key=lambda t: (affinity.get(tuple(sorted((last, t))), 0.0), incoming[t], t))
        order.append(nxt)
        remaining.discard(nxt)
    return order


def render(mapping: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    enc = _encoding(mapping)
    s_col, t_col, w_col = enc["source"], enc["target"], enc["width"]

    # Aggregate duplicate (source, target) pairs into one link (bare names).
    flows: dict[tuple[str, str], float] = {}
    order_pairs: list[tuple[str, str]] = []
    sources: list[str] = []
    targets: list[str] = []
    for r in rows:
        if s_col not in r or t_col not in r or w_col not in r:
            continue
        try:
            w = float(r[w_col])
        except (TypeError, ValueError):
            continue
        s, t = str(r[s_col]), str(r[t_col])
        if s not in sources:
            sources.append(s)
        if t not in targets:
            targets.append(t)
        key = (s, t)
        if key not in flows:
            flows[key] = 0.0
            order_pairs.append(key)
        flows[key] += w

    # Per-node weights and the source -> [(target, weight)] adjacency.
    incoming: dict[str, float] = {t: 0.0 for t in targets}
    outgoing: dict[str, float] = {s: 0.0 for s in sources}
    src_links: dict[str, list[tuple[str, float]]] = {s: [] for s in sources}
    for (s, t), w in flows.items():
        incoming[t] += w
        outgoing[s] += w
        src_links[s].append((t, w))

    # Step A: target affinity matrix, then seriate.
    affinity: dict[tuple[str, str], float] = {}
    for lst in src_links.values():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                (ta, wa), (tb, wb) = lst[i], lst[j]
                k = tuple(sorted((ta, tb)))
                affinity[k] = affinity.get(k, 0.0) + min(wa, wb)
    target_order = _seriate_targets(targets, affinity, incoming)
    target_rank = {t: i for i, t in enumerate(target_order)}

    # Step B: source weighted barycentre, then sort.
    def barycentre(s: str) -> float:
        tot = outgoing[s]
        return sum(w * target_rank[t] for t, w in src_links[s]) / tot if tot else 0.0

    source_order = sorted(sources, key=lambda s: (barycentre(s), -outgoing[s], s))
    source_rank = {s: i for i, s in enumerate(source_order)}

    # Nodes carry their integer order (Step C is enforced in JS via linkSort using node.order).
    nodes = [{"name": "src:" + s, "label": html.escape(s), "order": source_rank[s]} for s in sources]
    nodes += [{"name": "tgt:" + t, "label": html.escape(t), "order": target_rank[t]} for t in targets]
    links = [{"source": "src:" + s, "target": "tgt:" + t, "value": flows[(s, t)]} for (s, t) in order_pairs]

    # Pattern only affects the subtitle wording; explicit hint wins, else infer
    # (overlapping source/target value sets ⇒ the same set on both sides ⇒ reflexive).
    pattern = str(mapping.get("pattern", "")).lower()
    if "reflexive" in pattern:
        reflexive = True
    elif "many_many" in pattern:
        reflexive = False
    else:
        reflexive = bool(set(sources) & set(targets))
    frame = ("Reflexive: the same entity set on both sides (left = as source, right = as target)."
             if reflexive else "Sources (left) and targets (right) are two different entity sets.")

    title = html.escape(mapping.get("title") or (s_col + " → " + t_col + " Sankey diagram"))
    subtitle = html.escape("Link width represents '" + w_col + "'. " + frame
                           + " Targets ordered by affinity, sources by barycentre.")
    width = 1000
    height = max(700, max(len(sources), len(targets)) * 14 + 40)

    return (
        HEAD.replace("__T__", title).replace("__SUB__", subtitle)
        + "const nodes = " + json.dumps(nodes) + ";\n"
        + "const links = " + json.dumps(links) + ";\n"
        + "const width = " + str(width) + ", height = " + str(height) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a many-many Sankey diagram to standalone HTML (D3 v7).")
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
