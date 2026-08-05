import argparse
import json
import html
import pathlib


def render(mapping: dict, rows: list) -> str:
    # ------------------------------------------------------------------ #
    # 1. Read mapping fields                                               #
    # ------------------------------------------------------------------ #
    src_col = mapping["source"]
    tgt_col = mapping["target"]
    val_col = mapping.get("value", mapping.get("width", "count"))
    title   = mapping.get("title", "Force-directed Graph")
    pattern = mapping.get("pattern", "")

    # ------------------------------------------------------------------ #
    # 2. Build edges from rows                                             #
    # ------------------------------------------------------------------ #
    raw_edges = {}   # (src_raw, tgt_raw) -> weight
    for row in rows:
        s = row.get(src_col)
        t = row.get(tgt_col)
        if s is None or t is None:
            continue
        s = str(s)
        t = str(t)
        if val_col == "count":
            w = 1.0
        else:
            try:
                w = float(row.get(val_col, 1) or 1)
            except (TypeError, ValueError):
                w = 1.0
        key = (s, t)
        raw_edges[key] = raw_edges.get(key, 0.0) + w

    # ------------------------------------------------------------------ #
    # 3. Determine pattern (reflexive vs bipartite)                        #
    # ------------------------------------------------------------------ #
    all_sources = set(k[0] for k in raw_edges)
    all_targets = set(k[1] for k in raw_edges)

    if pattern == "reflexive_many_many_relationship":
        is_bipartite = False
    elif pattern == "many_many_relationship":
        is_bipartite = True
    else:
        # Infer: bipartite when the two value sets are disjoint
        is_bipartite = all_sources.isdisjoint(all_targets)

    # ------------------------------------------------------------------ #
    # 4. Build nodes                                                       #
    # ------------------------------------------------------------------ #
    if is_bipartite:
        # Namespace: "0::<value>" for sources, "1::<value>" for targets
        src_ids = {v: "0::" + v for v in sorted(all_sources)}
        tgt_ids = {v: "1::" + v for v in sorted(all_targets)}

        nodes_list = []
        for v in sorted(all_sources):
            nodes_list.append({"id": src_ids[v], "label": v, "group": 0})
        for v in sorted(all_targets):
            nodes_list.append({"id": tgt_ids[v], "label": v, "group": 1})

        links_list = []
        for (s, t), w in raw_edges.items():
            links_list.append({"source": src_ids[s], "target": tgt_ids[t], "w": w})

        # Derive group labels from mapping column names
        group0_label = html.escape(str(src_col))
        group1_label = html.escape(str(tgt_col))
    else:
        # Reflexive: union of both sides, undirected (canonicalise pair)
        all_vals = sorted(all_sources | all_targets)
        node_idx = {v: i for i, v in enumerate(all_vals)}
        nodes_list = [{"id": v, "label": v, "group": 0} for v in all_vals]

        collapsed = {}
        for (s, t), w in raw_edges.items():
            if s == t:
                continue   # skip self-loops
            key = (min(s, t), max(s, t))
            collapsed[key] = collapsed.get(key, 0.0) + w

        links_list = []
        for (s, t), w in collapsed.items():
            links_list.append({"source": s, "target": t, "w": w})

        group0_label = ""
        group1_label = ""

    # ------------------------------------------------------------------ #
    # 5. Escape all string data before injecting                           #
    # ------------------------------------------------------------------ #
    def escape_nodes(nlist):
        out = []
        for n in nlist:
            out.append({
                "id":    html.escape(str(n["id"])),
                "label": html.escape(str(n["label"])),
                "group": n["group"]
            })
        return out

    def escape_links(llist):
        out = []
        for lk in llist:
            out.append({
                "source": html.escape(str(lk["source"])),
                "target": html.escape(str(lk["target"])),
                "w":      lk["w"]
            })
        return out

    nodes_escaped = escape_nodes(nodes_list)
    links_escaped = escape_links(links_list)

    def safe_json(obj):
        return json.dumps(obj).replace("</", "<\\/")

    nodes_json   = safe_json(nodes_escaped)
    links_json   = safe_json(links_escaped)
    title_safe   = html.escape(str(title))
    is_bip_json  = safe_json(is_bipartite)
    g0_json      = safe_json(group0_label)
    g1_json      = safe_json(group1_label)
    src_col_safe = html.escape(str(src_col))
    tgt_col_safe = html.escape(str(tgt_col))
    val_col_safe = html.escape(str(val_col))

    # ------------------------------------------------------------------ #
    # 6. Build HTML via string concatenation (no f-strings / .format)     #
    # ------------------------------------------------------------------ #

    html_parts = []

    html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>""")
    html_parts.append(title_safe)
    html_parts.append("""</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #f7f7f7; font-family: 'Segoe UI', Arial, sans-serif; color: #333; }
  #chart-wrapper {
    display: flex; flex-direction: column; align-items: center;
    padding: 24px 16px 32px;
  }
  h1 { font-size: 1.25rem; font-weight: 700; margin-bottom: 4px; text-align: center; }
  .subtitle { font-size: 0.78rem; color: #666; margin-bottom: 16px; text-align: center; }
  #chart-container {
    position: relative;
    width: 100%;
    max-width: 1100px;
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.09);
    overflow: visible;
    display: flex;
    justify-content: center;
  }
  svg { display: block; margin: 0 auto; }
  .link { stroke: #999; stroke-opacity: 0.35; fill: none; }
  .node circle {
    stroke: #fff; stroke-width: 1.5px; cursor: pointer;
  }
  .node text {
    font-size: 10px; fill: #444; pointer-events: none;
    text-shadow: 0 1px 2px #fff, 0 -1px 2px #fff, 1px 0 2px #fff, -1px 0 2px #fff;
  }
  #tooltip {
    position: fixed;
    background: rgba(30,30,30,0.88);
    color: #fff;
    padding: 7px 11px;
    border-radius: 5px;
    font-size: 12px;
    pointer-events: none;
    display: none;
    z-index: 9999;
    max-width: 260px;
    line-height: 1.5;
  }
  .legend { display: flex; gap: 18px; margin-top: 12px; align-items: center; flex-wrap: wrap; justify-content: center; }
  .legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #555; }
  .legend-swatch { width: 13px; height: 13px; border-radius: 50%; display: inline-block; }
  #no-data {
    padding: 40px; font-size: 1rem; color: #888; text-align: center;
  }
</style>
</head>
<body>
<div id="chart-wrapper">
  <h1>""")
    html_parts.append(title_safe)
    html_parts.append("""</h1>
  <div class="subtitle" id="subtitle"></div>
  <div id="chart-container">
    <div id="no-data" style="display:none">No data to display.</div>
  </div>
  <div class="legend" id="legend"></div>
</div>
<div id="tooltip"></div>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
(function() {
"use strict";

const NODES      = """ + nodes_json + """;
const LINKS      = """ + links_json + """;
const IS_BIPARTITE = """ + is_bip_json + """;
const GROUP0_LABEL = """ + g0_json + """;
const GROUP1_LABEL = """ + g1_json + """;
const VAL_COL    = """ + safe_json(val_col_safe) + """;

// ── Graceful empty-data handling ─────────────────────────────────────────
if (NODES.length === 0 || LINKS.length === 0) {
  document.getElementById("no-data").style.display = "block";
  document.getElementById("subtitle").textContent  = "No data to display.";
  return;
}

// ── Degree map ────────────────────────────────────────────────────────────
const degreeMap = new Map(NODES.map(n => [n.id, 0]));
LINKS.forEach(lk => {
  degreeMap.set(lk.source, (degreeMap.get(lk.source) || 0) + 1);
  degreeMap.set(lk.target, (degreeMap.get(lk.target) || 0) + 1);
});

// Drop isolated nodes (degree 0)
const hiddenCount = NODES.filter(n => degreeMap.get(n.id) === 0).length;
const activeNodes = NODES.filter(n => degreeMap.get(n.id) > 0);

if (activeNodes.length === 0) {
  document.getElementById("no-data").style.display = "block";
  document.getElementById("subtitle").textContent  = "No data to display.";
  return;
}

// ── Subtitle ──────────────────────────────────────────────────────────────
const valDesc = (VAL_COL === "count") ? "edge count" : VAL_COL;
let subtitleText = "Node size \u2192 degree \u00b7 Link width \u2192 " + valDesc;
if (hiddenCount > 0) subtitleText += " \u00b7 " + hiddenCount + " isolated node(s) hidden";
document.getElementById("subtitle").textContent = subtitleText;

// ── Dimensions ────────────────────────────────────────────────────────────
const W = Math.min(window.innerWidth - 40, 1060);
const H = Math.max(620, Math.round(W * 0.65));
const cx = W / 2, cy = H / 2;

const svg = d3.select("#chart-container")
  .append("svg")
  .attr("width",  W)
  .attr("height", H);

const g = svg.append("g");

// ── Scales ────────────────────────────────────────────────────────────────
const maxDeg = d3.max(activeNodes, d => degreeMap.get(d.id)) || 1;
const maxW   = d3.max(LINKS, d => d.w) || 1;

const rScale = d3.scaleSqrt()
  .domain([0, maxDeg])
  .range([3, 14]);

const linkWScale = d3.scaleSqrt()
  .domain([0, maxW])
  .range([0.8, 6]);

// Colour scales
const colorBip = d3.scaleOrdinal()
  .domain([0, 1])
  .range(["#4e79a7", "#f28e2b"]);

const colorRefl = d3.scaleSequential()
  .domain([0, maxDeg])
  .interpolator(d3.interpolateViridis);

function nodeColor(d) {
  if (IS_BIPARTITE) return colorBip(d.group);
  return colorRefl(degreeMap.get(d.id) || 0);
}

// ── Seed node positions deterministically on a circle ────────────────────
const n = activeNodes.length;
activeNodes.forEach((d, i) => {
  const angle = (2 * Math.PI * i) / n;
  const r0    = Math.min(W, H) * 0.32;
  d.x = cx + r0 * Math.cos(angle);
  d.y = cy + r0 * Math.sin(angle);
});

// ── Force simulation ──────────────────────────────────────────────────────
const linkForce = d3.forceLink(LINKS)
  .id(d => d.id)
  .distance(lk => {
    const sd = degreeMap.get(typeof lk.source === "object" ? lk.source.id : lk.source) || 1;
    const td = degreeMap.get(typeof lk.target === "object" ? lk.target.id : lk.target) || 1;
    return 30 + 80 / Math.sqrt((sd + td) / 2);
  })
  .strength(IS_BIPARTITE ? 0.15 : 0.3);

const chargeForce = d3.forceManyBody()
  .strength(d => -60 - 20 * (degreeMap.get(d.id) || 0))
  .distanceMax(Math.min(W, H) * 0.55);

const collideForce = d3.forceCollide()
  .radius(d => rScale(degreeMap.get(d.id) || 0) + 5)
  .iterations(3);

const sim = d3.forceSimulation(activeNodes)
  .force("link",    linkForce)
  .force("charge",  chargeForce)
  .force("collide", collideForce);

if (IS_BIPARTITE) {
  // Bipartite: pull two groups to opposite sides
  sim.force("x", d3.forceX(d => d.group === 0 ? W * 0.27 : W * 0.73).strength(0.28));
  sim.force("y", d3.forceY(cy).strength(0.06));
} else {
  // Reflexive: gentle centring
  sim.force("center", d3.forceCenter(cx, cy).strength(0.05));
  sim.force("x", d3.forceX(cx).strength(0.04));
  sim.force("y", d3.forceY(cy).strength(0.04));
}

// Pre-run 120 ticks to settle before first paint (keeps simulation live)
sim.stop();
for (let i = 0; i < 120; i++) sim.tick();
sim.restart();

// ── Draw links ────────────────────────────────────────────────────────────
// Gentle curved links: a quadratic arc separates near-parallel edges, which raises
// crossing angles and reduces the "solid mass" look of overlapping straight lines.
function linkPath(d) {
  const x1 = d.source.x, y1 = d.source.y, x2 = d.target.x, y2 = d.target.y;
  const dx = x2 - x1, dy = y2 - y1;
  const dr = Math.hypot(dx, dy) || 1;
  const curv = 0.18;                 // sag as a fraction of link length
  const mx = (x1 + x2) / 2 - dy / dr * dr * curv;
  const my = (y1 + y2) / 2 + dx / dr * dr * curv;
  return "M" + x1 + "," + y1 + "Q" + mx + "," + my + " " + x2 + "," + y2;
}
const linkSel = g.append("g").attr("class", "links")
  .selectAll("path")
  .data(LINKS)
  .join("path")
  .attr("class", "link")
  .attr("fill", "none")
  .attr("stroke-width", d => linkWScale(d.w));

// ── Draw nodes ────────────────────────────────────────────────────────────
const nodeSel = g.append("g").attr("class", "nodes")
  .selectAll("g")
  .data(activeNodes)
  .join("g")
  .attr("class", "node");

nodeSel.append("circle")
  .attr("r",    d => rScale(degreeMap.get(d.id) || 0))
  .attr("fill", d => nodeColor(d));

const labelSel = nodeSel.append("text")
  .attr("dy", d => -rScale(degreeMap.get(d.id) || 0) - 3)
  .attr("text-anchor", "middle")
  .text(d => d.label)
  .style("display", "none");   // shown selectively after layout

// ── Tooltip ───────────────────────────────────────────────────────────────
const tooltip = d3.select("#tooltip");

function showTooltip(event, html) {
  tooltip.style("display", "block")
    .html(html)
    .style("left", (event.clientX + 14) + "px")
    .style("top",  (event.clientY - 28) + "px");
}
function moveTooltip(event) {
  tooltip.style("left", (event.clientX + 14) + "px")
         .style("top",  (event.clientY - 28) + "px");
}
function hideTooltip() { tooltip.style("display", "none"); }

// ── Node adjacency map ────────────────────────────────────────────────────
function buildAdjacency() {
  const adj = new Map();
  LINKS.forEach(lk => {
    const sid = typeof lk.source === "object" ? lk.source.id : lk.source;
    const tid = typeof lk.target === "object" ? lk.target.id : lk.target;
    if (!adj.has(sid)) adj.set(sid, new Set());
    if (!adj.has(tid)) adj.set(tid, new Set());
    adj.get(sid).add(tid);
    adj.get(tid).add(sid);
  });
  return adj;
}
let adj = buildAdjacency();

// ── Highlight helpers ─────────────────────────────────────────────────────
function highlightNode(d) {
  const neighbours = adj.get(d.id) || new Set();
  nodeSel.selectAll("circle")
    .style("opacity", nd => (nd.id === d.id || neighbours.has(nd.id)) ? 1 : 0.12);
  nodeSel.selectAll("text")
    .style("opacity", nd => (nd.id === d.id || neighbours.has(nd.id)) ? 1 : 0.08);
  linkSel
    .style("stroke-opacity", lk => {
      const sid = typeof lk.source === "object" ? lk.source.id : lk.source;
      const tid = typeof lk.target === "object" ? lk.target.id : lk.target;
      return (sid === d.id || tid === d.id) ? 0.85 : 0.04;
    })
    .style("stroke", lk => {
      const sid = typeof lk.source === "object" ? lk.source.id : lk.source;
      const tid = typeof lk.target === "object" ? lk.target.id : lk.target;
      return (sid === d.id || tid === d.id) ? "#e15759" : "#999";
    });
}

function highlightLink(lk) {
  const sid = typeof lk.source === "object" ? lk.source.id : lk.source;
  const tid = typeof lk.target === "object" ? lk.target.id : lk.target;
  nodeSel.selectAll("circle")
    .style("opacity", nd => (nd.id === sid || nd.id === tid) ? 1 : 0.12);
  linkSel
    .style("stroke-opacity", l => l === lk ? 0.9 : 0.04)
    .style("stroke", l => l === lk ? "#e15759" : "#999");
}

function resetHighlight() {
  nodeSel.selectAll("circle").style("opacity", 1);
  nodeSel.selectAll("text").style("opacity", null);
  linkSel.style("stroke-opacity", 0.35).style("stroke", "#999");
}

// ── Node interactions ─────────────────────────────────────────────────────
nodeSel
  .on("mouseover", function(event, d) {
    highlightNode(d);
    const deg = degreeMap.get(d.id) || 0;
    let tipHtml = "<strong>" + d.label + "</strong><br/>Degree: " + deg;
    if (IS_BIPARTITE) {
      tipHtml += "<br/>Group: " + (d.group === 0 ? GROUP0_LABEL : GROUP1_LABEL);
    }
    showTooltip(event, tipHtml);
  })
  .on("mousemove", moveTooltip)
  .on("mouseout", function() { resetHighlight(); hideTooltip(); });

// ── Link interactions ─────────────────────────────────────────────────────
linkSel
  .on("mouseover", function(event, lk) {
    highlightLink(lk);
    const sid = typeof lk.source === "object" ? lk.source.label : lk.source;
    const tid = typeof lk.target === "object" ? lk.target.label : lk.target;
    const tipHtml = "<strong>" + sid + "</strong> \u2194 <strong>" + tid +
                    "</strong><br/>Weight: " + lk.w.toFixed(2);
    showTooltip(event, tipHtml);
  })
  .on("mousemove", moveTooltip)
  .on("mouseout", function() { resetHighlight(); hideTooltip(); });

// ── Drag ──────────────────────────────────────────────────────────────────
nodeSel.call(
  d3.drag()
    .on("start", function(event, d) {
      if (!event.active) sim.alphaTarget(0.3).restart();
      d.fx = d.x; d.fy = d.y;
    })
    .on("drag", function(event, d) {
      d.fx = event.x; d.fy = event.y;
    })
    .on("end", function(event, d) {
      if (!event.active) sim.alphaTarget(0);
      d.fx = null; d.fy = null;
    })
);

// ── Tick handler ──────────────────────────────────────────────────────────
sim.on("tick", function() {
  linkSel.attr("d", linkPath);
  nodeSel.attr("transform", d => "translate(" + d.x + "," + d.y + ")");
});

// ── Refit viewBox + declutter labels on simulation end ───────────────────
sim.on("end", function() {
  adj = buildAdjacency();   // refresh after simulation resolves ids

  // Guard: check all positions are finite
  const allFinite = activeNodes.every(d => isFinite(d.x) && isFinite(d.y));
  if (!allFinite) return;

  // Refit viewBox
  try {
    const bb = g.node().getBBox();
    const pad = 28;
    svg
      .attr("viewBox", (bb.x - pad) + " " + (bb.y - pad) + " " +
                       (bb.width + 2*pad) + " " + (bb.height + 2*pad))
      .attr("width",  bb.width  + 2*pad)
      .attr("height", bb.height + 2*pad);
  } catch(e) { /* getBBox may fail in headless env */ }

  // Declutter labels: show top-degree nodes whose labels don't overlap
  const sorted = activeNodes.slice().sort((a, b) =>
    (degreeMap.get(b.id) || 0) - (degreeMap.get(a.id) || 0)
  );

  // Show top candidates first, then do overlap check
  const topK = Math.min(sorted.length, Math.max(6, Math.round(activeNodes.length * 0.15)));
  const candidates = sorted.slice(0, topK);

  // First pass: show them all
  candidates.forEach(d => {
    nodeSel.filter(nd => nd.id === d.id).select("text").style("display", null);
  });

  // Second pass: greedy overlap removal using getBBox
  const kept = [];
  candidates.forEach(d => {
    const textEl = nodeSel.filter(nd => nd.id === d.id).select("text").node();
    if (!textEl) return;
    let bb2;
    try { bb2 = textEl.getBBox(); } catch(e) { return; }
    const overlaps = kept.some(kb => !(
      bb2.x > kb.x + kb.width  ||
      bb2.x + bb2.width < kb.x ||
      bb2.y > kb.y + kb.height ||
      bb2.y + bb2.height < kb.y
    ));
    if (overlaps) {
      d3.select(textEl).style("display", "none");
    } else {
      kept.push(bb2);
    }
  });
});

// ── Legend (bipartite only) ───────────────────────────────────────────────
if (IS_BIPARTITE) {
  const legendEl = document.getElementById("legend");
  [[0, GROUP0_LABEL], [1, GROUP1_LABEL]].forEach(function(pair) {
    const grp = pair[0], lbl = pair[1];
    const item = document.createElement("div");
    item.className = "legend-item";
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.background = colorBip(grp);
    const txt = document.createTextNode(lbl);
    item.appendChild(swatch);
    item.appendChild(txt);
    legendEl.appendChild(item);
  });
}

// ── Reflexive: colour legend (gradient) ──────────────────────────────────
if (!IS_BIPARTITE) {
  const legendEl = document.getElementById("legend");
  const svgLeg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svgLeg.setAttribute("width", "160");
  svgLeg.setAttribute("height", "18");
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  const grad = document.createElementNS("http://www.w3.org/2000/svg", "linearGradient");
  grad.setAttribute("id", "legGrad");
  [0, 0.25, 0.5, 0.75, 1].forEach(function(t) {
    const stop = document.createElementNS("http://www.w3.org/2000/svg", "stop");
    stop.setAttribute("offset", (t*100) + "%");
    stop.setAttribute("stop-color", d3.interpolateViridis(t));
    grad.appendChild(stop);
  });
  defs.appendChild(grad);
  svgLeg.appendChild(defs);
  const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  rect.setAttribute("x","0"); rect.setAttribute("y","0");
  rect.setAttribute("width","120"); rect.setAttribute("height","12");
  rect.setAttribute("fill","url(#legGrad)");
  svgLeg.appendChild(rect);
  const t1 = document.createElementNS("http://www.w3.org/2000/svg", "text");
  t1.setAttribute("x","0"); t1.setAttribute("y","18");
  t1.setAttribute("font-size","9"); t1.setAttribute("fill","#666");
  t1.textContent = "low degree";
  svgLeg.appendChild(t1);
  const t2 = document.createElementNS("http://www.w3.org/2000/svg", "text");
  t2.setAttribute("x","120"); t2.setAttribute("y","18");
  t2.setAttribute("font-size","9"); t2.setAttribute("fill","#666");
  t2.setAttribute("text-anchor","end");
  t2.textContent = "high degree";
  svgLeg.appendChild(t2);

  const item = document.createElement("div");
  item.className = "legend-item";
  item.appendChild(svgLeg);
  legendEl.appendChild(item);
}

})();
</script>
</body>
</html>""")

    return "".join(html_parts)


# ──────────────────────────────────────────────────────────────────────────── #
# CLI                                                                          #
# ──────────────────────────────────────────────────────────────────────────── #

def main():
    parser = argparse.ArgumentParser(description="Force-directed graph renderer for Mondial")
    parser.add_argument("--mapping", required=True, help="Path to mapping JSON file")
    parser.add_argument("--data",    required=True, help="Path to data JSON file (array or grouped DB)")
    parser.add_argument("--out",     required=True, help="Output HTML file path")
    args = parser.parse_args()

    mapping_path = pathlib.Path(args.mapping)
    data_path    = pathlib.Path(args.data)
    out_path     = pathlib.Path(args.out)

    with mapping_path.open("r", encoding="utf-8") as f:
        mapping = json.load(f)

    # Accept bare mapping or a Stage-1/2 result object
    if "chart_mapping" in mapping:
        mapping = mapping["chart_mapping"]
    elif "selected_visualisation" in mapping:
        mapping = mapping["selected_visualisation"].get("encoding", mapping)

    with data_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    # Detect grouped Mondial DB vs plain array
    if isinstance(raw, dict) and "tables" in raw:
        table = mapping.get("table", "")
        rows = raw["tables"].get(table, [])
    elif isinstance(raw, list):
        rows = raw
    else:
        rows = []

    html_out = render(mapping, rows)

    with out_path.open("w", encoding="utf-8") as f:
        f.write(html_out)

    print("Written:", out_path)


if __name__ == "__main__":
    main()


# # # import argparse
# # # import json
# # # import html
# # # import pathlib


# # # def render(mapping: dict, rows: list) -> str:
# # #     # ------------------------------------------------------------------ #
# # #     # 0.  Read mapping fields                                              #
# # #     # ------------------------------------------------------------------ #
# # #     src_col = mapping["source"]
# # #     tgt_col = mapping["target"]
# # #     val_col = mapping.get("value", mapping.get("width", "count"))
# # #     title   = mapping.get("title", "Force-Directed Graph")
# # #     pattern = mapping.get("pattern", "")

# # #     # ------------------------------------------------------------------ #
# # #     # 1.  Build raw edges from rows                                        #
# # #     # ------------------------------------------------------------------ #
# # #     raw_edges = []
# # #     for row in rows:
# # #         s = row.get(src_col)
# # #         t = row.get(tgt_col)
# # #         if s is None or t is None:
# # #             continue
# # #         s = str(s)
# # #         t = str(t)
# # #         if val_col == "count":
# # #             w = 1.0
# # #         else:
# # #             try:
# # #                 w = float(row.get(val_col, 1) or 1)
# # #             except (TypeError, ValueError):
# # #                 w = 1.0
# # #         raw_edges.append((s, t, w))

# # #     # ------------------------------------------------------------------ #
# # #     # 2.  Detect bipartite vs reflexive                                    #
# # #     # ------------------------------------------------------------------ #
# # #     src_values = {e[0] for e in raw_edges}
# # #     tgt_values = {e[1] for e in raw_edges}

# # #     if pattern == "many_many_relationship":
# # #         bipartite = True
# # #     elif pattern == "reflexive_many_many_relationship":
# # #         bipartite = False
# # #     else:
# # #         # Infer: if the two value sets are disjoint → bipartite
# # #         bipartite = src_values.isdisjoint(tgt_values)

# # #     # ------------------------------------------------------------------ #
# # #     # 3.  Build nodes and links                                            #
# # #     # ------------------------------------------------------------------ #
# # #     if bipartite:
# # #         # Namespace ids so same-label nodes on different sides are distinct
# # #         src_id  = lambda v: "src::" + v
# # #         tgt_id  = lambda v: "tgt::" + v

# # #         all_src = sorted(src_values)
# # #         all_tgt = sorted(tgt_values)

# # #         nodes = []
# # #         node_index = {}
# # #         for v in all_src:
# # #             nid = src_id(v)
# # #             node_index[nid] = len(nodes)
# # #             nodes.append({
# # #                 "id":    html.escape(nid),
# # #                 "label": html.escape(v),
# # #                 "group": 0
# # #             })
# # #         for v in all_tgt:
# # #             nid = tgt_id(v)
# # #             node_index[nid] = len(nodes)
# # #             nodes.append({
# # #                 "id":    html.escape(nid),
# # #                 "label": html.escape(v),
# # #                 "group": 1
# # #             })

# # #         # Collapse parallel edges (directed for bipartite)
# # #         edge_map = {}
# # #         for s, t, w in raw_edges:
# # #             key = (src_id(s), tgt_id(t))
# # #             edge_map[key] = edge_map.get(key, 0.0) + w

# # #         links = [
# # #             {"source": html.escape(k[0]),
# # #              "target": html.escape(k[1]),
# # #              "w":      v}
# # #             for k, v in sorted(edge_map.items())
# # #         ]

# # #         src_label  = html.escape(str(src_col))
# # #         tgt_label  = html.escape(str(tgt_col))
# # #         legend_html = (
# # #             "<div style='display:flex;gap:18px;align-items:center;"
# # #             "font-size:12px;color:#555;margin-bottom:4px;'>"
# # #             "<span><span style='display:inline-block;width:12px;height:12px;"
# # #             "border-radius:50%;background:#4e79a7;margin-right:4px;'></span>"
# # #             + src_label +
# # #             "</span>"
# # #             "<span><span style='display:inline-block;width:12px;height:12px;"
# # #             "border-radius:50%;background:#f28e2b;margin-right:4px;'></span>"
# # #             + tgt_label +
# # #             "</span></div>"
# # #         )

# # #     else:
# # #         # Reflexive: one node set, undirected edges
# # #         all_nodes = sorted(src_values | tgt_values)
# # #         nodes = []
# # #         node_index = {}
# # #         for v in all_nodes:
# # #             node_index[v] = len(nodes)
# # #             nodes.append({
# # #                 "id":    html.escape(v),
# # #                 "label": html.escape(v),
# # #                 "group": 0
# # #             })

# # #         # Canonicalise undirected pairs
# # #         edge_map = {}
# # #         for s, t, w in raw_edges:
# # #             if s == t:
# # #                 continue
# # #             key = (min(s, t), max(s, t))
# # #             edge_map[key] = edge_map.get(key, 0.0) + w

# # #         links = [
# # #             {"source": html.escape(k[0]),
# # #              "target": html.escape(k[1]),
# # #              "w":      v}
# # #             for k, v in sorted(edge_map.items())
# # #         ]
# # #         legend_html = ""

# # #     # ------------------------------------------------------------------ #
# # #     # 4.  Empty-data guard                                                 #
# # #     # ------------------------------------------------------------------ #
# # #     if not nodes or not links:
# # #         escaped_title = html.escape(title)
# # #         return (
# # #             "<!DOCTYPE html><html><head><meta charset='utf-8'>"
# # #             "<title>" + escaped_title + "</title></head><body>"
# # #             "<p style='font-family:sans-serif;padding:2em;color:#555'>"
# # #             "No data to display.</p></body></html>"
# # #         )

# # #     # ------------------------------------------------------------------ #
# # #     # 5.  Serialise to JSON (script-safe)                                  #
# # #     # ------------------------------------------------------------------ #
# # #     def js_safe(x):
# # #         return json.dumps(x).replace("</", "<\\/")

# # #     nodes_json  = js_safe(nodes)
# # #     links_json  = js_safe(links)
# # #     title_json  = js_safe(html.escape(title))
# # #     is_bip_json = js_safe(bipartite)
# # #     val_label   = js_safe(html.escape("count" if val_col == "count" else str(val_col)))

# # #     # ------------------------------------------------------------------ #
# # #     # 6.  Build HTML via string concatenation (no f-strings / .format)    #
# # #     # ------------------------------------------------------------------ #
# # #     subtitle = (
# # #         "Node size = degree  |  Link width = "
# # #         + html.escape("count" if val_col == "count" else str(val_col))
# # #     )

# # #     html_parts = []
# # #     html_parts.append("""<!DOCTYPE html>
# # # <html lang="en">
# # # <head>
# # # <meta charset="utf-8">
# # # <meta name="viewport" content="width=device-width,initial-scale=1">
# # # <title>""")
# # #     html_parts.append(html.escape(title))
# # #     html_parts.append("""</title>
# # # <style>
# # #   body { margin:0; background:#fafafa; font-family:'Segoe UI',Arial,sans-serif; }
# # #   #chart-wrap {
# # #     display:flex; flex-direction:column; align-items:center;
# # #     padding:24px 16px 32px;
# # #   }
# # #   h1 { font-size:18px; font-weight:600; color:#222; margin:0 0 2px; text-align:center; }
# # #   .subtitle { font-size:12px; color:#888; margin:0 0 10px; text-align:center; }
# # #   #legend { margin-bottom:6px; }
# # #   #graph-svg { display:block; }
# # #   .tooltip {
# # #     position:fixed; pointer-events:none; background:rgba(30,30,30,.88);
# # #     color:#fff; border-radius:5px; padding:7px 11px; font-size:12px;
# # #     line-height:1.5; white-space:pre-wrap; max-width:260px;
# # #     box-shadow:0 2px 8px rgba(0,0,0,.35); display:none; z-index:999;
# # #   }
# # # </style>
# # # </head>
# # # <body>
# # # <div id="chart-wrap">
# # #   <h1>""")
# # #     html_parts.append(html.escape(title))
# # #     html_parts.append("""</h1>
# # #   <p class="subtitle">""")
# # #     html_parts.append(subtitle)
# # #     html_parts.append("""</p>
# # #   <div id="legend">""")
# # #     html_parts.append(legend_html)
# # #     html_parts.append("""</div>
# # #   <svg id="graph-svg"></svg>
# # # </div>
# # # <div class="tooltip" id="tip"></div>
# # # <script src="https://d3js.org/d3.v7.min.js"></script>
# # # <script>
# # # (function () {
# # #   "use strict";

# # #   // ── injected data ──────────────────────────────────────────────────
# # #   const NODES     = """ + nodes_json + """;
# # #   const LINKS     = """ + links_json + """;
# # #   const IS_BIP    = """ + is_bip_json + """;
# # #   const VAL_LABEL = """ + val_label + """;
# # #   const TITLE     = """ + title_json + """;

# # #   // ── dimensions ────────────────────────────────────────────────────
# # #   const W = Math.min(window.innerWidth - 32, 960);
# # #   const H = Math.max(560, Math.round(W * 0.65));

# # #   const svg = d3.select("#graph-svg")
# # #     .attr("width",  W)
# # #     .attr("height", H)
# # #     .attr("viewBox", [0, 0, W, H]);

# # #   // defs: arrowhead (optional, not used for undirected but kept for bipartite)
# # #   const defs = svg.append("defs");

# # #   // ── scales ────────────────────────────────────────────────────────
# # #   // degree map
# # #   const degMap = new Map();
# # #   NODES.forEach(n => degMap.set(n.id, 0));
# # #   LINKS.forEach(l => {
# # #     const sid = typeof l.source === "object" ? l.source.id : l.source;
# # #     const tid = typeof l.target === "object" ? l.target.id : l.target;
# # #     degMap.set(sid, (degMap.get(sid) || 0) + 1);
# # #     degMap.set(tid, (degMap.get(tid) || 0) + 1);
# # #   });

# # #   const maxDeg = d3.max(Array.from(degMap.values())) || 1;
# # #   const rScale = d3.scaleSqrt().domain([0, maxDeg]).range([3, 14]);

# # #   const maxW = d3.max(LINKS, d => d.w) || 1;
# # #   const wScale = d3.scaleSqrt().domain([0, maxW]).range([0.8, 6]);

# # #   // colour
# # #   const bipColour = d3.scaleOrdinal()
# # #     .domain([0, 1])
# # #     .range(["#4e79a7", "#f28e2b"]);

# # #   const refColour = d3.scaleSequential()
# # #     .domain([0, maxDeg])
# # #     .interpolator(d3.interpolateViridis);

# # #   function nodeColour(d) {
# # #     if (IS_BIP) return bipColour(d.group);
# # #     return refColour(degMap.get(d.id) || 0);
# # #   }

# # #   // ── seed positions on a circle (determinism) ──────────────────────
# # #   const cx = W / 2, cy = H / 2;
# # #   const initR = Math.min(W, H) * 0.38;
# # #   NODES.forEach((n, i) => {
# # #     const angle = (2 * Math.PI * i) / NODES.length;
# # #     n.x = cx + initR * Math.cos(angle);
# # #     n.y = cy + initR * Math.sin(angle);
# # #   });

# # #   // ── simulation ────────────────────────────────────────────────────
# # #   const sim = d3.forceSimulation(NODES)
# # #     .force("link", d3.forceLink(LINKS)
# # #       .id(d => d.id)
# # #       .distance(d => {
# # #         const sid = typeof d.source === "object" ? d.source.id : d.source;
# # #         const tid = typeof d.target === "object" ? d.target.id : d.target;
# # #         const avgDeg = ((degMap.get(sid) || 1) + (degMap.get(tid) || 1)) / 2;
# # #         return Math.max(40, 120 / Math.sqrt(avgDeg));
# # #       })
# # #       .strength(0.4)
# # #     )
# # #     .force("charge", d3.forceManyBody().strength(d => {
# # #       const deg = degMap.get(d.id) || 1;
# # #       return -60 - deg * 4;
# # #     }))
# # #     .force("center", d3.forceCenter(cx, cy).strength(0.05))
# # #     .force("collide", d3.forceCollide(d => rScale(degMap.get(d.id) || 0) + 3))
# # #     .alphaDecay(0.03)
# # #     .velocityDecay(0.4);

# # #   // ── DOM elements ──────────────────────────────────────────────────
# # #   const linkG = svg.append("g").attr("class", "links");
# # #   const nodeG = svg.append("g").attr("class", "nodes");
# # #   const labelG = svg.append("g").attr("class", "labels").attr("pointer-events", "none");

# # #   const linkSel = linkG.selectAll("line")
# # #     .data(LINKS)
# # #     .join("line")
# # #       .attr("stroke", "#999")
# # #       .attr("stroke-opacity", 0.35)
# # #       .attr("stroke-width", d => wScale(d.w));

# # #   const nodeSel = nodeG.selectAll("circle")
# # #     .data(NODES)
# # #     .join("circle")
# # #       .attr("r", d => rScale(degMap.get(d.id) || 0))
# # #       .attr("fill", nodeColour)
# # #       .attr("stroke", "#fff")
# # #       .attr("stroke-width", 1.5)
# # #       .attr("cursor", "pointer");

# # #   // Label only top-degree nodes (top 15 % or at least 1)
# # #   const degThreshold = d3.quantile(
# # #     Array.from(degMap.values()).sort(d3.ascending),
# # #     0.85
# # #   ) || 0;

# # #   const labelSel = labelG.selectAll("text")
# # #     .data(NODES.filter(n => (degMap.get(n.id) || 0) >= degThreshold))
# # #     .join("text")
# # #       .attr("font-size", 10)
# # #       .attr("fill", "#333")
# # #       .attr("text-anchor", "middle")
# # #       .attr("dy", "0.35em")
# # #       .text(d => d.label);

# # #   // ── tooltip ───────────────────────────────────────────────────────
# # #   const tip = d3.select("#tip");

# # #   function showTip(event, html) {
# # #     tip.style("display", "block")
# # #        .html(html)
# # #        .style("left", (event.clientX + 14) + "px")
# # #        .style("top",  (event.clientY - 10) + "px");
# # #   }
# # #   function moveTip(event) {
# # #     tip.style("left", (event.clientX + 14) + "px")
# # #        .style("top",  (event.clientY - 10) + "px");
# # #   }
# # #   function hideTip() { tip.style("display", "none"); }

# # #   // ── highlight helpers ─────────────────────────────────────────────
# # #   function neighbourSet(d) {
# # #     const s = new Set([d.id]);
# # #     LINKS.forEach(l => {
# # #       const sid = l.source.id || l.source;
# # #       const tid = l.target.id || l.target;
# # #       if (sid === d.id) s.add(tid);
# # #       if (tid === d.id) s.add(sid);
# # #     });
# # #     return s;
# # #   }

# # #   nodeSel
# # #     .on("mouseover", function (event, d) {
# # #       const nbrs = neighbourSet(d);
# # #       nodeSel.attr("opacity", n => nbrs.has(n.id) ? 1 : 0.15);
# # #       linkSel.attr("stroke-opacity", l => {
# # #         const sid = l.source.id || l.source;
# # #         const tid = l.target.id || l.target;
# # #         return (sid === d.id || tid === d.id) ? 0.8 : 0.05;
# # #       });
# # #       d3.select(this).attr("stroke", "#222").attr("stroke-width", 2.5);
# # #       const deg = degMap.get(d.id) || 0;
# # #       showTip(event,
# # #         "<strong>" + d.label + "</strong><br>Degree: " + deg
# # #       );
# # #     })
# # #     .on("mousemove", moveTip)
# # #     .on("mouseout", function () {
# # #       nodeSel.attr("opacity", 1);
# # #       linkSel.attr("stroke-opacity", 0.35);
# # #       d3.select(this).attr("stroke", "#fff").attr("stroke-width", 1.5);
# # #       hideTip();
# # #     });

# # #   linkSel
# # #     .on("mouseover", function (event, d) {
# # #       const sid = d.source.id || d.source;
# # #       const tid = d.target.id || d.target;
# # #       const sLabel = (NODES.find(n => n.id === sid) || {label: sid}).label;
# # #       const tLabel = (NODES.find(n => n.id === tid) || {label: tid}).label;
# # #       nodeSel.attr("opacity", n => (n.id === sid || n.id === tid) ? 1 : 0.15);
# # #       linkSel.attr("stroke-opacity", l => l === d ? 0.9 : 0.05);
# # #       d3.select(this).attr("stroke", "#e15759").attr("stroke-opacity", 1);
# # #       showTip(event,
# # #         "<strong>" + sLabel + "</strong> ↔ <strong>" + tLabel + "</strong>"
# # #         + "<br>" + VAL_LABEL + ": " + d.w
# # #       );
# # #     })
# # #     .on("mousemove", moveTip)
# # #     .on("mouseout", function () {
# # #       nodeSel.attr("opacity", 1);
# # #       linkSel.attr("stroke-opacity", 0.35).attr("stroke", "#999");
# # #       hideTip();
# # #     });

# # #   // ── drag ──────────────────────────────────────────────────────────
# # #   nodeSel.call(
# # #     d3.drag()
# # #       .on("start", (event, d) => {
# # #         if (!event.active) sim.alphaTarget(0.3).restart();
# # #         d.fx = d.x; d.fy = d.y;
# # #       })
# # #       .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
# # #       .on("end",  (event, d) => {
# # #         if (!event.active) sim.alphaTarget(0);
# # #         d.fx = null; d.fy = null;
# # #       })
# # #   );

# # #   // ── tick ──────────────────────────────────────────────────────────
# # #   sim.on("tick", () => {
# # #     // Soft bounding: nudge nodes back toward the visible area
# # #     NODES.forEach(n => {
# # #       const r = rScale(degMap.get(n.id) || 0);
# # #       if (isFinite(n.x)) n.x = Math.max(r, Math.min(W - r, n.x));
# # #       if (isFinite(n.y)) n.y = Math.max(r, Math.min(H - r, n.y));
# # #     });

# # #     linkSel
# # #       .attr("x1", d => d.source.x)
# # #       .attr("y1", d => d.source.y)
# # #       .attr("x2", d => d.target.x)
# # #       .attr("y2", d => d.target.y);

# # #     nodeSel
# # #       .attr("cx", d => d.x)
# # #       .attr("cy", d => d.y);

# # #     labelSel
# # #       .attr("x", d => d.x)
# # #       .attr("y", d => d.y - rScale(degMap.get(d.id) || 0) - 4);
# # #   });

# # #   // ── refit viewBox after simulation settles ────────────────────────
# # #   sim.on("end", () => {
# # #     try {
# # #       const bbox = svg.node().getBBox();
# # #       if (!isFinite(bbox.x) || !isFinite(bbox.y) ||
# # #           !isFinite(bbox.width) || !isFinite(bbox.height) ||
# # #           bbox.width === 0 || bbox.height === 0) return;
# # #       const pad = 20;
# # #       const vx = bbox.x - pad;
# # #       const vy = bbox.y - pad;
# # #       const vw = bbox.width  + pad * 2;
# # #       const vh = bbox.height + pad * 2;
# # #       svg.attr("viewBox", [vx, vy, vw, vh].join(" "))
# # #          .attr("width",  Math.min(vw, window.innerWidth - 32))
# # #          .attr("height", Math.min(vh, window.innerHeight - 120));
# # #     } catch (e) { /* getBBox may throw in hidden tabs */ }
# # #   });

# # # })();
# # # </script>
# # # </body>
# # # </html>
# # # """)

# # #     return "".join(html_parts)


# # # # ------------------------------------------------------------------ #
# # # # CLI                                                                  #
# # # # ------------------------------------------------------------------ #
# # # def main():
# # #     parser = argparse.ArgumentParser(description="Force-directed graph renderer")
# # #     parser.add_argument("--mapping", required=True, help="Path to mapping JSON file")
# # #     parser.add_argument("--data",    required=True, help="Path to data JSON file")
# # #     parser.add_argument("--out",     required=True, help="Path for output HTML file")
# # #     args = parser.parse_args()

# # #     mapping_path = pathlib.Path(args.mapping)
# # #     data_path    = pathlib.Path(args.data)
# # #     out_path     = pathlib.Path(args.out)

# # #     with mapping_path.open(encoding="utf-8") as fh:
# # #         mapping = json.load(fh)

# # #     # Accept bare mapping or a Stage-1/2 result wrapper
# # #     if "chart_mapping" in mapping:
# # #         mapping = mapping["chart_mapping"]
# # #     elif "selected_visualisation" in mapping:
# # #         sv = mapping["selected_visualisation"]
# # #         mapping = sv.get("encoding", sv)

# # #     with data_path.open(encoding="utf-8") as fh:
# # #         raw = json.load(fh)

# # #     # Accept grouped Mondial DB or plain array
# # #     if isinstance(raw, dict) and "tables" in raw:
# # #         table = mapping.get("table", "")
# # #         rows = raw["tables"].get(table, [])
# # #     elif isinstance(raw, list):
# # #         rows = raw
# # #     else:
# # #         rows = []

# # #     html_out = render(mapping, rows)

# # #     out_path.write_text(html_out, encoding="utf-8")
# # #     print("Written:", out_path)


# # # if __name__ == "__main__":
# # #     main()

  
# # import argparse
# # import json
# # import html
# # import pathlib


# # def render(mapping: dict, rows: list) -> str:
# #     # --- Read mapping fields ---
# #     source_col = mapping["source"]
# #     target_col = mapping["target"]
# #     value_col = mapping.get("value", mapping.get("width", "count"))
# #     pattern = mapping.get("pattern", "")
# #     title = mapping.get("title", "Force-Directed Graph")

# #     # --- Determine pattern ---
# #     # Collect raw source/target values
# #     raw_sources = set()
# #     raw_targets = set()
# #     for row in rows:
# #         s = row.get(source_col)
# #         t = row.get(target_col)
# #         if s is not None:
# #             raw_sources.add(str(s))
# #         if t is not None:
# #             raw_targets.add(str(t))

# #     if not pattern:
# #         # Infer: if sets are disjoint -> many_many, else reflexive
# #         if raw_sources.isdisjoint(raw_targets):
# #             pattern = "many_many_relationship"
# #         else:
# #             pattern = "reflexive_many_many_relationship"

# #     is_bipartite = (pattern == "many_many_relationship")

# #     # --- Build nodes and links ---
# #     if is_bipartite:
# #         # Namespace: source nodes get prefix "s__", target nodes get prefix "t__"
# #         source_label_col = mapping.get("source_label", source_col)
# #         target_label_col = mapping.get("target_label", target_col)

# #         node_map = {}  # namespaced_id -> {id, label, group}

# #         for row in rows:
# #             s = row.get(source_col)
# #             t = row.get(target_col)
# #             if s is None or t is None:
# #                 continue
# #             s_str = str(s)
# #             t_str = str(t)
# #             s_id = "s__" + s_str
# #             t_id = "t__" + t_str
# #             if s_id not in node_map:
# #                 node_map[s_id] = {"id": s_id, "label": html.escape(s_str), "group": 0}
# #             if t_id not in node_map:
# #                 node_map[t_id] = {"id": t_id, "label": html.escape(t_str), "group": 1}

# #         # Build edge aggregation
# #         edge_map = {}  # (s_id, t_id) -> weight
# #         for row in rows:
# #             s = row.get(source_col)
# #             t = row.get(target_col)
# #             if s is None or t is None:
# #                 continue
# #             s_id = "s__" + str(s)
# #             t_id = "t__" + str(t)
# #             key = (s_id, t_id)
# #             if value_col == "count":
# #                 w = 1
# #             else:
# #                 try:
# #                     w = float(row.get(value_col, 1) or 1)
# #                 except (TypeError, ValueError):
# #                     w = 1
# #             edge_map[key] = edge_map.get(key, 0) + w

# #         group0_label = html.escape(source_col)
# #         group1_label = html.escape(target_col)

# #     else:
# #         # Reflexive: one node set
# #         node_map = {}
# #         for row in rows:
# #             s = row.get(source_col)
# #             t = row.get(target_col)
# #             if s is None or t is None:
# #                 continue
# #             for v in [str(s), str(t)]:
# #                 if v not in node_map:
# #                     node_map[v] = {"id": v, "label": html.escape(v), "group": 0}

# #         # Build edge aggregation (undirected: canonicalise order)
# #         edge_map = {}
# #         for row in rows:
# #             s = row.get(source_col)
# #             t = row.get(target_col)
# #             if s is None or t is None:
# #                 continue
# #             s_str = str(s)
# #             t_str = str(t)
# #             if s_str == t_str:
# #                 continue  # skip self-loops
# #             a, b = (s_str, t_str) if s_str < t_str else (t_str, s_str)
# #             key = (a, b)
# #             if value_col == "count":
# #                 w = 1
# #             else:
# #                 try:
# #                     w = float(row.get(value_col, 1) or 1)
# #                 except (TypeError, ValueError):
# #                     w = 1
# #             edge_map[key] = edge_map.get(key, 0) + w

# #         group0_label = ""
# #         group1_label = ""

# #     # --- Handle empty data ---
# #     if not node_map or not edge_map:
# #         escaped_title = html.escape(title)
# #         return (
# #             "<!DOCTYPE html><html><head><meta charset='utf-8'>"
# #             "<title>" + escaped_title + "</title></head>"
# #             "<body style='font-family:sans-serif;display:flex;align-items:center;"
# #             "justify-content:center;height:100vh;margin:0;'>"
# #             "<p style='font-size:1.5em;color:#666;'>No data to display</p>"
# #             "</body></html>"
# #         )

# #     # --- Compute degrees for nodes ---
# #     degree = {nid: 0 for nid in node_map}
# #     for (a, b) in edge_map:
# #         if a in degree:
# #             degree[a] = degree.get(a, 0) + 1
# #         if b in degree:
# #             degree[b] = degree.get(b, 0) + 1

# #     # --- Drop isolated nodes (degree 0) ---
# #     # (After building edge_map, any node not in any edge has degree 0)
# #     # Count them for subtitle
# #     isolated_count = sum(1 for nid in node_map if degree.get(nid, 0) == 0)
# #     active_nodes = {nid: node_map[nid] for nid in node_map if degree.get(nid, 0) > 0}

# #     if not active_nodes:
# #         escaped_title = html.escape(title)
# #         return (
# #             "<!DOCTYPE html><html><head><meta charset='utf-8'>"
# #             "<title>" + escaped_title + "</title></head>"
# #             "<body style='font-family:sans-serif;display:flex;align-items:center;"
# #             "justify-content:center;height:100vh;margin:0;'>"
# #             "<p style='font-size:1.5em;color:#666;'>No data to display</p>"
# #             "</body></html>"
# #         )

# #     # --- Build final nodes list (sorted for determinism) ---
# #     if is_bipartite:
# #         sorted_nodes = sorted(active_nodes.values(), key=lambda n: (n["group"], n["label"]))
# #     else:
# #         sorted_nodes = sorted(active_nodes.values(), key=lambda n: n["label"])

# #     # Assign degree to each node
# #     for n in sorted_nodes:
# #         n["degree"] = degree.get(n["id"], 0)

# #     # --- Build final links list ---
# #     sorted_links = []
# #     active_ids = set(active_nodes.keys())
# #     for (a, b), w in sorted(edge_map.items()):
# #         if a in active_ids and b in active_ids:
# #             sorted_links.append({"source": a, "target": b, "w": w})

# #     # --- Escape ids for JSON injection ---
# #     # json.dumps handles escaping; we apply script-safety after
# #     def safe_json(obj):
# #         return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")

# #     nodes_json = safe_json(sorted_nodes)
# #     links_json = safe_json(sorted_links)
# #     title_json = safe_json(html.escape(title))
# #     is_bipartite_json = safe_json(is_bipartite)
# #     group0_label_json = safe_json(group0_label)
# #     group1_label_json = safe_json(group1_label)
# #     isolated_count_json = safe_json(isolated_count)
# #     value_col_json = safe_json(html.escape(value_col))
# #     source_col_json = safe_json(html.escape(source_col))
# #     target_col_json = safe_json(html.escape(target_col))

# #     # --- Build HTML ---
# #     # Use string concatenation + replace on __PLACEHOLDER__ tokens
# #     template = '''<!DOCTYPE html>
# # <html lang="en">
# # <head>
# # <meta charset="utf-8">
# # <title>__TITLE_RAW__</title>
# # <style>
# #   * { box-sizing: border-box; }
# #   body {
# #     margin: 0; padding: 0;
# #     background: #f8f8f8;
# #     font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
# #   }
# #   #chart-wrapper {
# #     width: 100%;
# #     display: flex;
# #     flex-direction: column;
# #     align-items: center;
# #     padding: 24px 16px 32px;
# #   }
# #   h1 {
# #     font-size: 1.3em;
# #     font-weight: 600;
# #     color: #222;
# #     margin: 0 0 4px 0;
# #     text-align: center;
# #   }
# #   #subtitle {
# #     font-size: 0.82em;
# #     color: #777;
# #     margin: 0 0 16px 0;
# #     text-align: center;
# #   }
# #   #svg-container {
# #     width: 100%;
# #     display: flex;
# #     justify-content: center;
# #   }
# #   svg {
# #     display: block;
# #     margin: 0 auto;
# #     background: #fff;
# #     border-radius: 6px;
# #     box-shadow: 0 1px 4px rgba(0,0,0,0.10);
# #     overflow: visible;
# #   }
# #   .link {
# #     stroke: #999;
# #     stroke-opacity: 0.35;
# #     fill: none;
# #     transition: stroke-opacity 0.15s;
# #   }
# #   .node circle {
# #     stroke: #fff;
# #     stroke-width: 1.5px;
# #     cursor: pointer;
# #     transition: opacity 0.15s;
# #   }
# #   .node text {
# #     pointer-events: none;
# #     font-size: 11px;
# #     fill: #333;
# #     dominant-baseline: central;
# #   }
# #   #tooltip {
# #     position: fixed;
# #     pointer-events: none;
# #     background: rgba(30,30,30,0.88);
# #     color: #fff;
# #     padding: 7px 11px;
# #     border-radius: 5px;
# #     font-size: 12px;
# #     line-height: 1.5;
# #     max-width: 260px;
# #     word-break: break-word;
# #     display: none;
# #     z-index: 999;
# #   }
# #   #legend {
# #     display: flex;
# #     gap: 18px;
# #     margin-top: 10px;
# #     font-size: 12px;
# #     color: #444;
# #     align-items: center;
# #     flex-wrap: wrap;
# #     justify-content: center;
# #   }
# #   .legend-item {
# #     display: flex;
# #     align-items: center;
# #     gap: 5px;
# #   }
# #   .legend-swatch {
# #     width: 13px;
# #     height: 13px;
# #     border-radius: 50%;
# #     display: inline-block;
# #     border: 1.5px solid #fff;
# #     box-shadow: 0 0 0 1px #ccc;
# #   }
# # </style>
# # </head>
# # <body>
# # <div id="chart-wrapper">
# #   <h1 id="chart-title"></h1>
# #   <div id="subtitle"></div>
# #   <div id="svg-container"></div>
# #   <div id="legend"></div>
# # </div>
# # <div id="tooltip"></div>
# # <script src="https://d3js.org/d3.v7.min.js"></script>
# # <script>
# # (function() {
# #   "use strict";

# #   const NODES = __NODES__;
# #   const LINKS = __LINKS__;
# #   const TITLE = __TITLE__;
# #   const IS_BIPARTITE = __IS_BIPARTITE__;
# #   const GROUP0_LABEL = __GROUP0_LABEL__;
# #   const GROUP1_LABEL = __GROUP1_LABEL__;
# #   const ISOLATED_COUNT = __ISOLATED_COUNT__;
# #   const VALUE_COL = __VALUE_COL__;
# #   const SOURCE_COL = __SOURCE_COL__;
# #   const TARGET_COL = __TARGET_COL__;

# #   // --- Title & subtitle ---
# #   document.getElementById("chart-title").textContent = TITLE;
# #   let subtitleParts = [];
# #   if (VALUE_COL === "count") {
# #     subtitleParts.push("Link width: edge count");
# #   } else {
# #     subtitleParts.push("Link width: " + VALUE_COL);
# #   }
# #   if (IS_BIPARTITE) {
# #     subtitleParts.push("Node size: degree");
# #   } else {
# #     subtitleParts.push("Node colour & size: degree");
# #   }
# #   if (ISOLATED_COUNT > 0) {
# #     subtitleParts.push(ISOLATED_COUNT + " isolated node" + (ISOLATED_COUNT > 1 ? "s" : "") + " hidden");
# #   }
# #   document.getElementById("subtitle").textContent = subtitleParts.join("  \u00b7  ");

# #   if (!NODES.length || !LINKS.length) {
# #     document.getElementById("chart-title").textContent = TITLE;
# #     document.getElementById("subtitle").textContent = "No data to display";
# #     return;
# #   }

# #   // --- Colour scales ---
# #   const color0 = "#4e79a7";
# #   const color1 = "#f28e2b";
# #   const reflexiveScale = d3.scaleSequential(d3.interpolateViridis);

# #   // --- Degree extent ---
# #   const degrees = NODES.map(function(n) { return n.degree; });
# #   const maxDeg = d3.max(degrees) || 1;
# #   const minDeg = d3.min(degrees) || 0;
# #   reflexiveScale.domain([minDeg, maxDeg]);

# #   function nodeColor(d) {
# #     if (IS_BIPARTITE) {
# #       return d.group === 0 ? color0 : color1;
# #     }
# #     return reflexiveScale(d.degree);
# #   }

# #   // --- Radius scale ---
# #   const rScale = d3.scaleSqrt()
# #     .domain([0, maxDeg])
# #     .range([3, 14]);

# #   function nodeRadius(d) {
# #     return Math.max(3, rScale(d.degree));
# #   }

# #   // --- Link width scale ---
# #   const wExtent = d3.extent(LINKS, function(l) { return l.w; });
# #   const wScale = d3.scaleSqrt()
# #     .domain([wExtent[0] || 0, wExtent[1] || 1])
# #     .range([0.8, 5]);

# #   // --- SVG setup (large initial canvas; will refit) ---
# #   const W = 960, H = 700;
# #   const svg = d3.select("#svg-container")
# #     .append("svg")
# #     .attr("width", W)
# #     .attr("height", H);

# #   const g = svg.append("g");

# #   // --- Seed node positions deterministically on a circle ---
# #   const cx = W / 2, cy = H / 2;
# #   const initR = Math.min(W, H) * 0.38;
# #   NODES.forEach(function(n, i) {
# #     const angle = (2 * Math.PI * i) / NODES.length;
# #     n.x = cx + initR * Math.cos(angle);
# #     n.y = cy + initR * Math.sin(angle);
# #   });

# #   // --- Build adjacency for highlight ---
# #   const adjSet = new Set();
# #   const nodeLinks = {};
# #   NODES.forEach(function(n) { nodeLinks[n.id] = []; });
# #   LINKS.forEach(function(l, i) {
# #     const s = typeof l.source === "object" ? l.source.id : l.source;
# #     const t = typeof l.target === "object" ? l.target.id : l.target;
# #     adjSet.add(s + "|||" + t);
# #     adjSet.add(t + "|||" + s);
# #   });

# #   function areAdj(a, b) {
# #     return adjSet.has(a + "|||" + b);
# #   }

# #   // --- Force simulation ---
# #   const nodeCount = NODES.length;
# #   const chargeStrength = function(d) {
# #     // Hubs repel harder; scale by degree
# #     return -30 - d.degree * 4;
# #   };

# #   // For bipartite: separate the two groups horizontally
# #   let forceXTarget = null;
# #   if (IS_BIPARTITE) {
# #     forceXTarget = d3.forceX(function(d) {
# #       return d.group === 0 ? W * 0.28 : W * 0.72;
# #     }).strength(0.08);
# #   } else {
# #     forceXTarget = d3.forceX(cx).strength(0.04);
# #   }

# #   const sim = d3.forceSimulation(NODES)
# #     .force("link", d3.forceLink(LINKS)
# #       .id(function(d) { return d.id; })
# #       .distance(function(l) {
# #         const sr = nodeRadius(typeof l.source === "object" ? l.source : NODES.find(function(n){ return n.id === l.source; }) || {degree:1});
# #         const tr = nodeRadius(typeof l.target === "object" ? l.target : NODES.find(function(n){ return n.id === l.target; }) || {degree:1});
# #         return 40 + sr + tr + (IS_BIPARTITE ? 30 : 0);
# #       })
# #       .strength(IS_BIPARTITE ? 0.25 : 0.4)
# #     )
# #     .force("charge", d3.forceManyBody().strength(chargeStrength))
# #     .force("x", forceXTarget)
# #     .force("y", d3.forceY(cy).strength(IS_BIPARTITE ? 0.04 : 0.04))
# #     .force("collide", d3.forceCollide(function(d) {
# #       return nodeRadius(d) + 5;
# #     }).iterations(2))
# #     .alphaDecay(0.02)
# #     .stop();

# #   // Run simulation synchronously for determinism
# #   const tickCount = Math.min(300, 10 + Math.ceil(Math.sqrt(nodeCount) * 15));
# #   for (let i = 0; i < tickCount; i++) {
# #     sim.tick();
# #   }

# #   // --- Draw links ---
# #   const linkSel = g.append("g").attr("class", "links")
# #     .selectAll("line")
# #     .data(LINKS)
# #     .enter().append("line")
# #     .attr("class", "link")
# #     .attr("stroke-width", function(d) { return wScale(d.w); })
# #     .attr("x1", function(d) { return d.source.x; })
# #     .attr("y1", function(d) { return d.source.y; })
# #     .attr("x2", function(d) { return d.target.x; })
# #     .attr("y2", function(d) { return d.target.y; });

# #   // --- Draw nodes ---
# #   const nodeSel = g.append("g").attr("class", "nodes")
# #     .selectAll("g")
# #     .data(NODES)
# #     .enter().append("g")
# #     .attr("class", "node")
# #     .attr("transform", function(d) { return "translate(" + d.x + "," + d.y + ")"; });

# #   nodeSel.append("circle")
# #     .attr("r", nodeRadius)
# #     .attr("fill", nodeColor);

# #   // --- Label only top-degree nodes (greedy de-overlap) ---
# #   // Sort by degree descending, then greedily assign labels
# #   const labelCandidates = NODES.slice().sort(function(a, b) { return b.degree - a.degree; });
# #   const maxLabels = Math.min(40, Math.max(5, Math.floor(nodeCount * 0.25)));
# #   const keptLabels = new Set();
# #   const labelBoxes = [];

# #   // We approximate label bbox as (x + r + 2, y - 5, labelLen * 6.5, 12)
# #   function approxBox(d) {
# #     const r = nodeRadius(d);
# #     const len = d.label.length;
# #     return { x: d.x + r + 2, y: d.y - 6, w: len * 6.2, h: 12 };
# #   }

# #   function overlaps(b1, b2) {
# #     return !(b1.x + b1.w < b2.x || b2.x + b2.w < b1.x ||
# #              b1.y + b1.h < b2.y || b2.y + b2.h < b1.y);
# #   }

# #   for (let i = 0; i < labelCandidates.length && keptLabels.size < maxLabels; i++) {
# #     const d = labelCandidates[i];
# #     const box = approxBox(d);
# #     let collision = false;
# #     for (let j = 0; j < labelBoxes.length; j++) {
# #       if (overlaps(box, labelBoxes[j])) { collision = true; break; }
# #     }
# #     if (!collision) {
# #       keptLabels.add(d.id);
# #       labelBoxes.push(box);
# #     }
# #   }

# #   nodeSel.append("text")
# #     .attr("x", function(d) { return nodeRadius(d) + 3; })
# #     .attr("y", 0)
# #     .text(function(d) { return d.label; })
# #     .style("display", function(d) { return keptLabels.has(d.id) ? null : "none"; });

# #   // --- Refit SVG via getBBox ---
# #   function refitSVG() {
# #     // Guard: check all positions are finite
# #     let allFinite = true;
# #     NODES.forEach(function(n) {
# #       if (!isFinite(n.x) || !isFinite(n.y)) allFinite = false;
# #     });
# #     if (!allFinite) return;

# #     try {
# #       const pad = 30;
# #       const bb = g.node().getBBox();
# #       if (!isFinite(bb.x) || !isFinite(bb.y) || !isFinite(bb.width) || !isFinite(bb.height)) return;
# #       const vx = bb.x - pad;
# #       const vy = bb.y - pad;
# #       const vw = bb.width + pad * 2;
# #       const vh = bb.height + pad * 2;
# #       svg.attr("viewBox", vx + " " + vy + " " + vw + " " + vh)
# #          .attr("width", Math.min(vw, window.innerWidth - 32))
# #          .attr("height", Math.min(vh, window.innerHeight * 0.85));
# #     } catch(e) { /* getBBox failed, leave as-is */ }
# #   }

# #   refitSVG();

# #   // --- Tooltip ---
# #   const tooltip = d3.select("#tooltip");

# #   function showTooltip(event, html) {
# #     tooltip.style("display", "block")
# #       .html(html)
# #       .style("left", (event.clientX + 14) + "px")
# #       .style("top", (event.clientY - 10) + "px");
# #   }
# #   function moveTooltip(event) {
# #     tooltip.style("left", (event.clientX + 14) + "px")
# #       .style("top", (event.clientY - 10) + "px");
# #   }
# #   function hideTooltip() {
# #     tooltip.style("display", "none");
# #   }

# #   // --- Node interactivity ---
# #   nodeSel
# #     .on("mouseover", function(event, d) {
# #       // Highlight this node + neighbours + incident links; dim rest
# #       nodeSel.selectAll("circle")
# #         .style("opacity", function(n) {
# #           return n.id === d.id || areAdj(d.id, n.id) ? 1.0 : 0.12;
# #         });
# #       nodeSel.selectAll("text")
# #         .style("opacity", function(n) {
# #           return n.id === d.id || areAdj(d.id, n.id) ? 1.0 : 0.12;
# #         });
# #       linkSel
# #         .style("stroke-opacity", function(l) {
# #           const s = l.source.id, t = l.target.id;
# #           return (s === d.id || t === d.id) ? 0.85 : 0.04;
# #         });

# #       // Show label for hovered node regardless
# #       d3.select(this).select("text").style("display", null).style("opacity", 1);

# #       const tipHtml = "<strong>" + d.label + "</strong><br/>Degree: " + d.degree;
# #       showTooltip(event, tipHtml);
# #     })
# #     .on("mousemove", function(event) {
# #       moveTooltip(event);
# #     })
# #     .on("mouseout", function() {
# #       nodeSel.selectAll("circle").style("opacity", 1);
# #       nodeSel.selectAll("text")
# #         .style("opacity", 1)
# #         .style("display", function(d) { return keptLabels.has(d.id) ? null : "none"; });
# #       linkSel.style("stroke-opacity", 0.35);
# #       hideTooltip();
# #     });

# #   // --- Link interactivity ---
# #   linkSel
# #     .on("mouseover", function(event, d) {
# #       const sLabel = d.source.label;
# #       const tLabel = d.target.label;
# #       const wLabel = VALUE_COL === "count" ? "Count" : VALUE_COL;
# #       const tipHtml = "<strong>" + sLabel + "</strong> \u2194 <strong>" + tLabel + "</strong><br/>"
# #         + wLabel + ": " + d.w;
# #       showTooltip(event, tipHtml);
# #       d3.select(this).style("stroke-opacity", 0.9).style("stroke", "#444");
# #     })
# #     .on("mousemove", function(event) {
# #       moveTooltip(event);
# #     })
# #     .on("mouseout", function() {
# #       hideTooltip();
# #       d3.select(this).style("stroke-opacity", 0.35).style("stroke", "#999");
# #     });

# #   // --- Legend (bipartite) ---
# #   if (IS_BIPARTITE) {
# #     const legendDiv = document.getElementById("legend");
# #     const items = [
# #       { color: color0, label: GROUP0_LABEL || SOURCE_COL },
# #       { color: color1, label: GROUP1_LABEL || TARGET_COL }
# #     ];
# #     items.forEach(function(item) {
# #       const div = document.createElement("div");
# #       div.className = "legend-item";
# #       const swatch = document.createElement("span");
# #       swatch.className = "legend-swatch";
# #       swatch.style.background = item.color;
# #       const txt = document.createElement("span");
# #       txt.textContent = item.label;
# #       div.appendChild(swatch);
# #       div.appendChild(txt);
# #       legendDiv.appendChild(div);
# #     });
# #   } else {
# #     // Reflexive: colour gradient legend
# #     const legendDiv = document.getElementById("legend");
# #     const gradId = "viridis-grad";
# #     const gradSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
# #     gradSvg.setAttribute("width", "160");
# #     gradSvg.setAttribute("height", "18");
# #     const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
# #     const grad = document.createElementNS("http://www.w3.org/2000/svg", "linearGradient");
# #     grad.setAttribute("id", gradId);
# #     grad.setAttribute("x1", "0%"); grad.setAttribute("x2", "100%");
# #     grad.setAttribute("y1", "0%"); grad.setAttribute("y2", "0%");
# #     const stops = [0, 0.25, 0.5, 0.75, 1.0];
# #     stops.forEach(function(t) {
# #       const stop = document.createElementNS("http://www.w3.org/2000/svg", "stop");
# #       stop.setAttribute("offset", (t * 100) + "%");
# #       stop.setAttribute("stop-color", d3.interpolateViridis(t));
# #       grad.appendChild(stop);
# #     });
# #     defs.appendChild(grad);
# #     gradSvg.appendChild(defs);
# #     const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
# #     rect.setAttribute("x", "0"); rect.setAttribute("y", "3");
# #     rect.setAttribute("width", "120"); rect.setAttribute("height", "10");
# #     rect.setAttribute("rx", "3");
# #     rect.setAttribute("fill", "url(#" + gradId + ")");
# #     gradSvg.appendChild(rect);
# #     legendDiv.style.alignItems = "center";
# #     const lowLabel = document.createElement("span");
# #     lowLabel.textContent = "Low degree";
# #     lowLabel.style.fontSize = "11px";
# #     lowLabel.style.color = "#666";
# #     const highLabel = document.createElement("span");
# #     highLabel.textContent = "High degree";
# #     highLabel.style.fontSize = "11px";
# #     highLabel.style.color = "#666";
# #     legendDiv.appendChild(lowLabel);
# #     legendDiv.appendChild(gradSvg);
# #     legendDiv.appendChild(highLabel);
# #   }

# # })();
# # </script>
# # </body>
# # </html>'''

# #     escaped_title_raw = html.escape(title)

# #     result = template
# #     result = result.replace("__NODES__", nodes_json)
# #     result = result.replace("__LINKS__", links_json)
# #     result = result.replace("__TITLE__", title_json)
# #     result = result.replace("__IS_BIPARTITE__", is_bipartite_json)
# #     result = result.replace("__GROUP0_LABEL__", group0_label_json)
# #     result = result.replace("__GROUP1_LABEL__", group1_label_json)
# #     result = result.replace("__ISOLATED_COUNT__", isolated_count_json)
# #     result = result.replace("__VALUE_COL__", value_col_json)
# #     result = result.replace("__SOURCE_COL__", source_col_json)
# #     result = result.replace("__TARGET_COL__", target_col_json)
# #     result = result.replace("__TITLE_RAW__", escaped_title_raw)

# #     return result


# # def main():
# #     parser = argparse.ArgumentParser(description="Force-directed graph renderer")
# #     parser.add_argument("--mapping", required=True, help="Path to mapping JSON file")
# #     parser.add_argument("--data", required=True, help="Path to data JSON file")
# #     parser.add_argument("--out", required=True, help="Path to output HTML file")
# #     args = parser.parse_args()

# #     mapping_path = pathlib.Path(args.mapping)
# #     data_path = pathlib.Path(args.data)
# #     out_path = pathlib.Path(args.out)

# #     with open(mapping_path, "r", encoding="utf-8") as f:
# #         mapping = json.load(f)

# #     with open(data_path, "r", encoding="utf-8") as f:
# #         raw_data = json.load(f)

# #     # Support both array and grouped Mondial database format
# #     if isinstance(raw_data, list):
# #         rows = raw_data
# #     elif isinstance(raw_data, dict) and "tables" in raw_data:
# #         table_name = mapping.get("table", "")
# #         if not table_name:
# #             raise ValueError("Mapping must include a 'table' field when data is in grouped format.")
# #         rows = raw_data["tables"].get(table_name, [])
# #     else:
# #         rows = []

# #     html_output = render(mapping, rows)

# #     with open(out_path, "w", encoding="utf-8") as f:
# #         f.write(html_output)

# #     print("Written to", out_path)


# # if __name__ == "__main__":
# #     main()


# import argparse
# import json
# import html
# import pathlib
# import collections


# # ---------------------------------------------------------------------------
# # helpers
# # ---------------------------------------------------------------------------

# def _escape(v):
#     """html-escape a scalar value for safe injection."""
#     return html.escape(str(v), quote=True)


# def _js(obj):
#     """Serialise obj to JSON and make it safe to embed inside a <script>."""
#     return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


# # ---------------------------------------------------------------------------
# # core renderer
# # ---------------------------------------------------------------------------

# def render(mapping: dict, rows: list) -> str:
#     # ------------------------------------------------------------------ #
#     # 0.  Read mapping fields                                              #
#     # ------------------------------------------------------------------ #
#     src_col = mapping["source"]
#     tgt_col = mapping["target"]
#     val_col = mapping.get("value") or mapping.get("width") or "count"
#     pattern = mapping.get("pattern", "")
#     title   = _escape(mapping.get("title", "Force-directed Graph"))

#     # Determine bipartite vs reflexive
#     is_bipartite = (pattern == "many_many_relationship")

#     # ------------------------------------------------------------------ #
#     # 1.  Build edge list from rows                                        #
#     # ------------------------------------------------------------------ #
#     edge_counts: dict = collections.defaultdict(float)

#     for row in rows:
#         s = row.get(src_col)
#         t = row.get(tgt_col)
#         if s is None or t is None:
#             continue
#         s = str(s)
#         t = str(t)
#         if val_col == "count":
#             w = 1.0
#         else:
#             raw = row.get(val_col, 1)
#             try:
#                 w = float(raw) if raw is not None else 1.0
#             except (TypeError, ValueError):
#                 w = 1.0

#         if is_bipartite:
#             key = ("s:" + s, "t:" + t)
#         else:
#             # undirected — canonicalise
#             a, b = ("s:" + s, "s:" + t) if s <= t else ("s:" + t, "s:" + s)
#             key = (a, b)
#         edge_counts[key] += w

#     # ------------------------------------------------------------------ #
#     # 2.  Build node + link structures                                     #
#     # ------------------------------------------------------------------ #
#     node_map: dict = {}   # namespaced_id -> {id, label, group}

#     def ensure_node(ns_id, label, group):
#         if ns_id not in node_map:
#             node_map[ns_id] = {"id": ns_id, "label": label, "group": group}

#     links_raw = []
#     for (ns_s, ns_t), w in edge_counts.items():
#         # derive labels from namespaced ids
#         lbl_s = ns_s[2:]   # strip "s:" or "t:"
#         lbl_t = ns_t[2:]
#         grp_s = 0 if ns_s.startswith("s:") else 1
#         grp_t = 0 if ns_t.startswith("s:") else 1
#         ensure_node(ns_s, lbl_s, grp_s)
#         ensure_node(ns_t, lbl_t, grp_t)
#         links_raw.append({"source": ns_s, "target": ns_t, "w": w})

#     # If not explicitly bipartite, check if source/target sets are disjoint
#     if not is_bipartite and not pattern:
#         src_vals = {k for k in node_map if k.startswith("s:") and node_map[k]["group"] == 0}
#         tgt_vals = {k for k in node_map if k.startswith("s:") and node_map[k]["group"] == 0}
#         # all nodes are group 0 in reflexive — that's correct

#     # Compute degree for each node
#     degree: dict = collections.defaultdict(int)
#     for lnk in links_raw:
#         degree[lnk["source"]] += 1
#         degree[lnk["target"]] += 1

#     # Drop isolated nodes (degree 0) — they can't appear here since every
#     # node was inserted from an edge, so degree >= 1 always.  Still guard.
#     nodes_list = [n for n in node_map.values() if degree.get(n["id"], 0) > 0]
#     hidden_count = len(node_map) - len(nodes_list)

#     # Sort for determinism
#     nodes_list.sort(key=lambda n: (n["group"], n["label"]))

#     # Attach degree to each node dict
#     for n in nodes_list:
#         n["degree"] = degree.get(n["id"], 0)

#     # Escape labels for safe DOM use
#     for n in nodes_list:
#         n["label"] = _escape(n["label"])

#     # Determine group names for legend
#     if is_bipartite:
#         grp0_name = _escape(src_col)
#         grp1_name = _escape(tgt_col)
#     else:
#         grp0_name = _escape(src_col)
#         grp1_name = ""

#     subtitle_parts = []
#     subtitle_parts.append("Node size → degree")
#     subtitle_parts.append("Link width → " + ("edge count" if val_col == "count" else _escape(val_col)))
#     if hidden_count:
#         subtitle_parts.append(str(hidden_count) + " isolated node(s) hidden")
#     subtitle = " · ".join(subtitle_parts)

#     # Serialise for JS injection
#     nodes_json = _js(nodes_list)
#     links_json = _js(links_raw)

#     # ------------------------------------------------------------------ #
#     # 3.  Assemble HTML                                                    #
#     # ------------------------------------------------------------------ #

#     # We use __PLACEHOLDER__ tokens and str.replace — no f-strings or .format()
#     TEMPLATE = """<!DOCTYPE html>
# <html lang="en">
# <head>
# <meta charset="utf-8"/>
# <meta name="viewport" content="width=device-width, initial-scale=1"/>
# <title>__TITLE__</title>
# <style>
#   * { box-sizing: border-box; margin: 0; padding: 0; }
#   body { background: #f7f7f7; font-family: "Segoe UI", Arial, sans-serif; color: #333; }
#   #chart-wrap {
#     display: flex; flex-direction: column; align-items: center;
#     padding: 24px 16px 32px;
#   }
#   h1 { font-size: 1.25rem; font-weight: 700; margin-bottom: 4px; text-align: center; }
#   .subtitle { font-size: 0.78rem; color: #777; margin-bottom: 16px; text-align: center; }
#   #svg-container { width: 100%; display: flex; justify-content: center; }
#   svg { display: block; margin: 0 auto; background: #fff;
#         border: 1px solid #e0e0e0; border-radius: 6px; }
#   .link { stroke: #999; stroke-opacity: 0.35; fill: none; }
#   .node circle { stroke: #fff; stroke-width: 1.5px; cursor: pointer; }
#   .node text { pointer-events: none; font-size: 10px; fill: #444; }
#   .legend-item text { font-size: 11px; fill: #555; }
#   #tooltip {
#     position: fixed; pointer-events: none;
#     background: rgba(30,30,30,0.88); color: #fff;
#     padding: 7px 11px; border-radius: 5px;
#     font-size: 12px; line-height: 1.5;
#     max-width: 260px; word-break: break-word;
#     display: none; z-index: 9999;
#   }
# </style>
# </head>
# <body>
# <div id="chart-wrap">
#   <h1>__TITLE__</h1>
#   <div class="subtitle">__SUBTITLE__</div>
#   <div id="svg-container"></div>
# </div>
# <div id="tooltip"></div>
# <script src="https://d3js.org/d3.v7.min.js"></script>
# <script>
# (function () {
#   "use strict";

#   // ── injected data ──────────────────────────────────────────────────
#   const IS_BIPARTITE = __IS_BIPARTITE__;
#   const GRP0_NAME    = __GRP0_NAME__;
#   const GRP1_NAME    = __GRP1_NAME__;
#   const nodes        = __NODES__;
#   const links        = __LINKS__;
#   // ──────────────────────────────────────────────────────────────────

#   // Empty-data guard
#   if (!nodes || nodes.length === 0) {
#     document.getElementById("svg-container").textContent = "No data to display.";
#     return;
#   }

#   // ── dimensions ────────────────────────────────────────────────────
#   const W = Math.max(700, Math.min(1200, window.innerWidth - 48));
#   const H = Math.max(520, Math.round(W * 0.68));
#   const cx = W / 2, cy = H / 2;

#   const svg = d3.select("#svg-container")
#     .append("svg")
#     .attr("width", W)
#     .attr("height", H)
#     .attr("viewBox", "0 0 " + W + " " + H);

#   const gLinks = svg.append("g").attr("class", "links-layer");
#   const gNodes = svg.append("g").attr("class", "nodes-layer");

#   // ── scales ────────────────────────────────────────────────────────
#   const maxDeg  = d3.max(nodes, d => d.degree) || 1;
#   const maxW    = d3.max(links, d => d.w) || 1;

#   const rScale = d3.scaleSqrt().domain([0, maxDeg]).range([3, 14]);
#   const wScale = d3.scaleSqrt().domain([0, maxW]).range([0.8, 6]);

#   // Colour
#   let colourFn;
#   if (IS_BIPARTITE) {
#     const pal = ["#4e79a7", "#f28e2b"];
#     colourFn = d => pal[d.group] || pal[0];
#   } else {
#     const degScale = d3.scaleSequential(d3.interpolateViridis).domain([0, maxDeg]);
#     colourFn = d => degScale(d.degree);
#   }

#   // ── seed positions deterministically on a circle ──────────────────
#   nodes.forEach((d, i) => {
#     const angle = (2 * Math.PI * i) / nodes.length;
#     const r0 = Math.min(W, H) * 0.35;
#     d.x = cx + r0 * Math.cos(angle);
#     d.y = cy + r0 * Math.sin(angle);
#   });

#   // ── force simulation ──────────────────────────────────────────────
#   const linkForce = d3.forceLink(links)
#     .id(d => d.id)
#     .distance(d => {
#       // longer distance for heavy links so hubs spread
#       return 40 + wScale(d.w) * 6;
#     })
#     .strength(IS_BIPARTITE ? 0.15 : 0.3);

#   const chargeStrength = d => {
#     // hubs repel harder
#     const base = IS_BIPARTITE ? -120 : -80;
#     return base - d.degree * (IS_BIPARTITE ? 8 : 5);
#   };

#   const sim = d3.forceSimulation(nodes)
#     .force("link",    linkForce)
#     .force("charge",  d3.forceManyBody().strength(chargeStrength))
#     .force("collide", d3.forceCollide(d => rScale(d.degree) + 6).iterations(2))
#     .force("center",  d3.forceCenter(cx, cy).strength(0.04));

#   if (IS_BIPARTITE) {
#     // Pull two groups toward opposite columns
#     sim.force("sepX", d3.forceX(d => d.group === 0 ? W * 0.28 : W * 0.72).strength(0.28));
#     sim.force("sepY", d3.forceY(cy).strength(0.04));
#   } else {
#     sim.force("gx", d3.forceX(cx).strength(0.03));
#     sim.force("gy", d3.forceY(cy).strength(0.03));
#   }

#   // ── draw links ────────────────────────────────────────────────────
#   const linkSel = gLinks.selectAll("line")
#     .data(links)
#     .join("line")
#     .attr("class", "link")
#     .attr("stroke-width", d => wScale(d.w));

#   // ── draw nodes ────────────────────────────────────────────────────
#   const nodeSel = gNodes.selectAll("g.node")
#     .data(nodes)
#     .join("g")
#     .attr("class", "node");

#   nodeSel.append("circle")
#     .attr("r", d => rScale(d.degree))
#     .attr("fill", colourFn);

#   // Labels: only top-degree nodes; de-overlap after layout settles
#   const TOP_N = Math.min(nodes.length, Math.max(10, Math.round(nodes.length * 0.25)));
#   const sorted = [...nodes].sort((a, b) => b.degree - a.degree);
#   const labelSet = new Set(sorted.slice(0, TOP_N).map(d => d.id));

#   const labelSel = nodeSel.append("text")
#     .attr("x", d => rScale(d.degree) + 3)
#     .attr("y", 4)
#     .text(d => labelSet.has(d.id) ? d.label : "")
#     .style("display", d => labelSet.has(d.id) ? null : "none");

#   // ── tooltip ───────────────────────────────────────────────────────
#   const tooltip = d3.select("#tooltip");

#   function showTip(event, html_str) {
#     tooltip.style("display", "block").html(html_str);
#     moveTip(event);
#   }
#   function moveTip(event) {
#     tooltip
#       .style("left", (event.clientX + 14) + "px")
#       .style("top",  (event.clientY - 28) + "px");
#   }
#   function hideTip() { tooltip.style("display", "none"); }

#   // ── highlight helpers ─────────────────────────────────────────────
#   // Build adjacency for quick lookup
#   const adjSet = new Set();
#   const nodeLinks = {};  // id -> [link, ...]
#   links.forEach(lk => {
#     const s = typeof lk.source === "object" ? lk.source.id : lk.source;
#     const t = typeof lk.target === "object" ? lk.target.id : lk.target;
#     adjSet.add(s + "|||" + t);
#     adjSet.add(t + "|||" + s);
#     if (!nodeLinks[s]) nodeLinks[s] = [];
#     if (!nodeLinks[t]) nodeLinks[t] = [];
#     nodeLinks[s].push(lk);
#     nodeLinks[t].push(lk);
#   });

#   function isAdj(a, b) { return adjSet.has(a + "|||" + b); }

#   function highlightNode(event, d) {
#     const hid = d.id;
#     nodeSel.select("circle")
#       .attr("opacity", nd => (nd.id === hid || isAdj(hid, nd.id)) ? 1.0 : 0.15);
#     linkSel
#       .attr("stroke-opacity", lk => {
#         const s = typeof lk.source === "object" ? lk.source.id : lk.source;
#         const t = typeof lk.target === "object" ? lk.target.id : lk.target;
#         return (s === hid || t === hid) ? 0.85 : 0.05;
#       })
#       .attr("stroke-width", lk => {
#         const s = typeof lk.source === "object" ? lk.source.id : lk.source;
#         const t = typeof lk.target === "object" ? lk.target.id : lk.target;
#         return (s === hid || t === hid) ? wScale(lk.w) * 1.8 : wScale(lk.w);
#       });
#     const tipHtml = "<strong>" + d.label + "</strong><br/>Degree: " + d.degree;
#     showTip(event, tipHtml);
#   }

#   function highlightLink(event, lk) {
#     const s = typeof lk.source === "object" ? lk.source : {id: lk.source, label: lk.source};
#     const t = typeof lk.target === "object" ? lk.target : {id: lk.target, label: lk.target};
#     nodeSel.select("circle")
#       .attr("opacity", nd => (nd.id === s.id || nd.id === t.id) ? 1.0 : 0.15);
#     linkSel
#       .attr("stroke-opacity", l => l === lk ? 0.9 : 0.05)
#       .attr("stroke-width",   l => l === lk ? wScale(l.w) * 2 : wScale(l.w));
#     const tipHtml = "<strong>" + s.label + "</strong> → <strong>" + t.label + "</strong><br/>Weight: " + lk.w;
#     showTip(event, tipHtml);
#   }

#   function resetHighlight() {
#     nodeSel.select("circle").attr("opacity", 1.0);
#     linkSel.attr("stroke-opacity", 0.35).attr("stroke-width", d => wScale(d.w));
#     hideTip();
#   }

#   // ── node interactions ─────────────────────────────────────────────
#   nodeSel
#     .on("mouseover", highlightNode)
#     .on("mousemove", moveTip)
#     .on("mouseout",  resetHighlight);

#   // ── link interactions ─────────────────────────────────────────────
#   linkSel
#     .on("mouseover", highlightLink)
#     .on("mousemove", moveTip)
#     .on("mouseout",  resetHighlight);

#   // ── drag ──────────────────────────────────────────────────────────
#   nodeSel.call(
#     d3.drag()
#       .on("start", (event, d) => {
#         if (!event.active) sim.alphaTarget(0.3).restart();
#         d.fx = d.x; d.fy = d.y;
#       })
#       .on("drag", (event, d) => {
#         d.fx = event.x; d.fy = event.y;
#       })
#       .on("end", (event, d) => {
#         if (!event.active) sim.alphaTarget(0);
#         d.fx = null; d.fy = null;
#       })
#   );

#   // ── tick ──────────────────────────────────────────────────────────
#   sim.on("tick", () => {
#     linkSel
#       .attr("x1", d => d.source.x)
#       .attr("y1", d => d.source.y)
#       .attr("x2", d => d.target.x)
#       .attr("y2", d => d.target.y);
#     nodeSel.attr("transform", d => "translate(" + d.x + "," + d.y + ")");
#   });

#   // ── refit viewBox after simulation settles ────────────────────────
#   const SETTLE_TICKS = 300;
#   sim.on("end", () => {
#     refitViewBox();
#     deoverlapLabels();
#   });

#   // Also refit after a fixed number of ticks in case "end" fires late
#   let tickCount = 0;
#   const origTick = sim.on("tick");  // already set above
#   // We use a separate listener approach via alphaDecay
#   // Instead: schedule a one-time refit after SETTLE_TICKS ms
#   setTimeout(() => {
#     refitViewBox();
#     deoverlapLabels();
#   }, SETTLE_TICKS * (1000 / 60));  // rough estimate

#   function refitViewBox() {
#     // Guard against NaN positions
#     const finite = nodes.filter(d => isFinite(d.x) && isFinite(d.y));
#     if (finite.length === 0) return;

#     const pad = 40;
#     const xs = finite.map(d => d.x);
#     const ys = finite.map(d => d.y);
#     const x0 = d3.min(xs) - pad;
#     const y0 = d3.min(ys) - pad;
#     const x1 = d3.max(xs) + pad;
#     const y1 = d3.max(ys) + pad;
#     const vw = x1 - x0;
#     const vh = y1 - y0;
#     if (vw > 0 && vh > 0) {
#       svg.attr("viewBox", x0 + " " + y0 + " " + vw + " " + vh)
#          .attr("width",  Math.min(vw, window.innerWidth - 48))
#          .attr("height", Math.min(vh, window.innerHeight * 1.5));
#     }
#   }

#   // ── greedy label de-overlap ───────────────────────────────────────
#   function deoverlapLabels() {
#     // Walk labels in descending degree; hide if bbox overlaps a kept one
#     const kept = [];
#     const byDeg = [...nodes].sort((a, b) => b.degree - a.degree);
#     byDeg.forEach(d => {
#       if (!labelSet.has(d.id)) return;
#       const el = nodeSel.filter(nd => nd.id === d.id).select("text").node();
#       if (!el) return;
#       try {
#         const bb = el.getBBox();
#         const overlaps = kept.some(kb =>
#           !(bb.x + bb.width  < kb.x ||
#             bb.x             > kb.x + kb.width ||
#             bb.y + bb.height < kb.y ||
#             bb.y             > kb.y + kb.height)
#         );
#         if (!overlaps) {
#           kept.push({x: bb.x, y: bb.y, width: bb.width, height: bb.height});
#         } else {
#           el.style.display = "none";
#         }
#       } catch(e) { /* getBBox may fail for hidden elements */ }
#     });
#   }

#   // ── legend (bipartite) ────────────────────────────────────────────
#   if (IS_BIPARTITE) {
#     const leg = svg.append("g").attr("class", "legend")
#       .attr("transform", "translate(16,16)");
#     const pal = ["#4e79a7", "#f28e2b"];
#     [GRP0_NAME, GRP1_NAME].forEach((name, i) => {
#       const g = leg.append("g")
#         .attr("class", "legend-item")
#         .attr("transform", "translate(0," + (i * 22) + ")");
#       g.append("circle").attr("r", 7).attr("cx", 7).attr("cy", 7)
#         .attr("fill", pal[i]);
#       g.append("text").attr("x", 18).attr("y", 12).text(name);
#     });
#   }

# })();
# </script>
# </body>
# </html>"""

#     # Inject all values
#     html_out = TEMPLATE
#     html_out = html_out.replace("__TITLE__",        title)
#     html_out = html_out.replace("__SUBTITLE__",     subtitle)
#     html_out = html_out.replace("__IS_BIPARTITE__", "true" if is_bipartite else "false")
#     html_out = html_out.replace("__GRP0_NAME__",    _js(grp0_name))
#     html_out = html_out.replace("__GRP1_NAME__",    _js(grp1_name))
#     html_out = html_out.replace("__NODES__",        nodes_json)
#     html_out = html_out.replace("__LINKS__",        links_json)

#     return html_out


# # ---------------------------------------------------------------------------
# # CLI
# # ---------------------------------------------------------------------------

# def main():
#     parser = argparse.ArgumentParser(description="Force-directed graph renderer")
#     parser.add_argument("--mapping", required=True, help="Path to mapping JSON file")
#     parser.add_argument("--data",    required=True, help="Path to data JSON file")
#     parser.add_argument("--out",     required=True, help="Output HTML file path")
#     args = parser.parse_args()

#     mapping_path = pathlib.Path(args.mapping)
#     data_path    = pathlib.Path(args.data)
#     out_path     = pathlib.Path(args.out)

#     with mapping_path.open(encoding="utf-8") as f:
#         mapping = json.load(f)

#     # Accept bare mapping or a Stage-1/2 result object
#     if "chart_mapping" in mapping:
#         mapping = mapping["chart_mapping"]
#     elif "selected_visualisation" in mapping:
#         sv = mapping["selected_visualisation"]
#         mapping = sv.get("encoding", sv)

#     with data_path.open(encoding="utf-8") as f:
#         raw = json.load(f)

#     # Accept full Mondial grouped DB or a plain array
#     if isinstance(raw, dict) and "tables" in raw:
#         table = mapping.get("table", "")
#         rows = raw["tables"].get(table, [])
#     elif isinstance(raw, list):
#         rows = raw
#     else:
#         rows = []

#     html_str = render(mapping, rows)

#     out_path.parent.mkdir(parents=True, exist_ok=True)
#     with out_path.open("w", encoding="utf-8") as f:
#         f.write(html_str)

#     print("Written:", out_path)


# if __name__ == "__main__":
#     main()

