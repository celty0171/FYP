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
