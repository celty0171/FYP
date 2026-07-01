"""Reference arc-diagram renderer for the reflexive relationship pattern (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_arc.md. An arc diagram
lays the instances of **one** entity set on an ordered 1-D axis and draws each
relationship as a semicircular arc above the axis. It serves **only**
``reflexive_many_many_relationship`` (both foreign keys reference the same set); a
`many_many` relationship has two distinct sets and is better read as a matrix, force
graph or Sankey. On an ordered axis, short arcs (local links) and long arcs
(long-range links) are immediately distinguishable, which chord obscures.

Arc thickness/opacity encodes a scalar ``value`` column, else the legacy ``width``
column, else the edge ``"count"`` (each edge weight 1). Nodes are ordered and sized by
their **unweighted degree** (number of neighbouring instances), kept separate from the
arc-thickness measure so the two encodings do not conflate. HTML assembled by plain
string concatenation.
Std-lib only; D3 v7; hover interaction.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


JS_BODY = """
const leftPad = 30, rightPad = 30, topPad = 16, bottomPad = 10;
const step = Math.max(6, Math.min(26, Math.floor(1100 / names.length)));
const w = step * names.length;
const x = d3.scalePoint().domain(d3.range(names.length)).range([0, w]);

// Each arc is a semicircle rising above the axis by half its span, so the tallest arc
// sets how much headroom the axis needs. Place the axis below the tallest arc and size
// the SVG to fit both the arcs (above) and the rotated labels (below) — no clipping.
let maxR = 0;
links.forEach(l => { const r = Math.abs(x(l.i) - x(l.j)) / 2; if (r > maxR) maxR = r; });
const baseY = maxR + topPad;
const maxNameLen = d3.max(names, s => s.length) || 1;
const labelSpace = maxNameLen * 6 + 16;

const svg = d3.select("#chart").append("svg")
  .attr("width", w + leftPad + rightPad)
  .attr("height", baseY + labelSpace + bottomPad);

const maxW = d3.max(links, l => l.w) || 1;
const wScale = d3.scaleSqrt().domain([0, maxW]).range([0.5, 5]);

const tip = d3.select("#tip");
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

// Arcs above the axis: a half-circle whose radius is half the span between endpoints.
const arc = svg.append("g").attr("transform", `translate(${leftPad},0)`)
  .attr("fill", "none").attr("stroke", "#4c78a8")
  .selectAll("path").data(links).join("path")
  .attr("stroke-width", d => wScale(d.w))
  .attr("stroke-opacity", 0.45)
  .attr("d", d => {
    const x1 = x(d.i), x2 = x(d.j), r = Math.abs(x2 - x1) / 2;
    return "M" + x1 + "," + baseY + " A" + r + "," + r + " 0 0,1 " + x2 + "," + baseY;
  })
  .on("mouseover", (event, d) => {
    arc.attr("stroke-opacity", a => (a === d) ? 0.95 : 0.05);
    node.attr("opacity", n => (n.k === d.i || n.k === d.j) ? 1 : 0.2);
    tip.style("opacity", 1).html(names[d.i] + " &harr; " + names[d.j] + "<br>" + valueLabel + ": "
      + (Number.isInteger(d.w) ? d.w : d.w.toFixed(2)));
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", () => { arc.attr("stroke-opacity", 0.45); node.attr("opacity", 1); tip.style("opacity", 0); });

const adj = names.map(() => new Set());
links.forEach(l => { adj[l.i].add(l.j); adj[l.j].add(l.i); });

const nodeG = svg.append("g").attr("transform", `translate(${leftPad},0)`);
const node = nodeG.selectAll("g").data(names.map((nm, k) => ({ nm, k }))).join("g");
node.append("circle")
  .attr("cx", d => x(d.k)).attr("cy", baseY).attr("r", d => 2 + Math.sqrt(deg[d.k]))
  .attr("fill", d => degColor(deg[d.k]));
node.append("text")
  .attr("transform", d => "translate(" + x(d.k) + "," + (baseY + 8) + ") rotate(90)")
  .attr("dy", "0.32em").attr("font-size", 9).text(d => d.nm);

node
  .on("mouseover", (event, d) => {
    const nb = adj[d.k];
    node.attr("opacity", o => (o.k === d.k || nb.has(o.k)) ? 1 : 0.2);
    arc.attr("stroke-opacity", a => (a.i === d.k || a.j === d.k) ? 0.9 : 0.05);
    tip.style("opacity", 1).html("<strong>" + d.nm + "</strong><br>degree: " + deg[d.k]);
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", () => { node.attr("opacity", 1); arc.attr("stroke-opacity", 0.45); tip.style("opacity", 0); });

function degColor(v) { return d3.interpolateViridis(maxDeg ? v / maxDeg : 0); }

// Fit the SVG viewport to all rendered content so nothing is ever clipped, whatever the
// data: the arcs rise above the baseline by up to half their span, so the drawing extent
// is only known after layout. getBBox() returns the tight box of every mark (including
// negative coordinates); resize the root <svg> to match.
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

    pattern = str(mapping.get("pattern", "")).lower()
    if "many_many" in pattern and "reflexive" not in pattern:
        raise ValueError("arc diagram serves only reflexive_many_many_relationship; got pattern=" + pattern)

    names = sorted({str(r[s_col]) for r in rows if s_col in r} | {str(r[t_col]) for r in rows if t_col in r})
    idx = {n: i for i, n in enumerate(names)}

    weights: dict[tuple[int, int], float] = {}
    for r in rows:
        if s_col not in r or t_col not in r:
            continue
        a, b = idx[str(r[s_col])], idx[str(r[t_col])]
        if a == b:
            continue
        i, j = (a, b) if a < b else (b, a)
        if v_col is None:
            w = 1.0
        else:
            try:
                w = float(r[v_col])
            except (TypeError, ValueError):
                continue
        weights[(i, j)] = weights.get((i, j), 0.0) + w

    # Node degree is the UNWEIGHTED count of incident edges (number of neighbouring
    # instances); the scalar `value` (e.g. border length) is kept only for arc thickness,
    # so node size and axis order do not double-encode the same measure.
    deg = [0] * len(names)
    for (i, j) in weights:
        deg[i] += 1
        deg[j] += 1
    order = sorted(range(len(names)), key=lambda k: (-deg[k], names[k]))
    new_pos = {old: pos for pos, old in enumerate(order)}
    disp_names = [names[old] for old in order]
    disp_deg = [deg[old] for old in order]
    links = [{"i": new_pos[i], "j": new_pos[j], "w": w} for (i, j), w in weights.items()]

    value_label = "count" if v_col is None else v_col
    default_title = s_col + " ↔ " + t_col + " arc diagram"
    title = html.escape(mapping.get("title") or default_title)
    subtitle = "Reflexive relationship on one ordered axis (nodes ordered and sized by number of neighbours); arc width encodes '" + value_label + "'."
    max_deg = max(disp_deg) if disp_deg else 0

    return (
        HEAD.replace("__T__", title).replace("__SUB__", html.escape(subtitle))
        + "const names = " + json.dumps([html.escape(x) for x in disp_names]) + ";\n"
        + "const deg = " + json.dumps(disp_deg) + ";\n"
        + "const maxDeg = " + json.dumps(max_deg) + ";\n"
        + "const links = " + json.dumps(links) + ";\n"
        + "const valueLabel = " + json.dumps(html.escape(value_label)) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a reflexive many-many arc diagram to standalone HTML (D3 v7).")
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
