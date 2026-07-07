import argparse
import json
import html
import pathlib


def render(mapping: dict, rows: list) -> str:
    # ------------------------------------------------------------------ #
    # 0.  Read mapping fields                                              #
    # ------------------------------------------------------------------ #
    src_col = mapping["source"]
    tgt_col = mapping["target"]
    val_col = mapping.get("value", mapping.get("width", "count"))
    title   = mapping.get("title", "Force-Directed Graph")
    pattern = mapping.get("pattern", "")

    # ------------------------------------------------------------------ #
    # 1.  Build raw edges from rows                                        #
    # ------------------------------------------------------------------ #
    raw_edges = []
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
        raw_edges.append((s, t, w))

    # ------------------------------------------------------------------ #
    # 2.  Detect bipartite vs reflexive                                    #
    # ------------------------------------------------------------------ #
    src_values = {e[0] for e in raw_edges}
    tgt_values = {e[1] for e in raw_edges}

    if pattern == "many_many_relationship":
        bipartite = True
    elif pattern == "reflexive_many_many_relationship":
        bipartite = False
    else:
        # Infer: if the two value sets are disjoint → bipartite
        bipartite = src_values.isdisjoint(tgt_values)

    # ------------------------------------------------------------------ #
    # 3.  Build nodes and links                                            #
    # ------------------------------------------------------------------ #
    if bipartite:
        # Namespace ids so same-label nodes on different sides are distinct
        src_id  = lambda v: "src::" + v
        tgt_id  = lambda v: "tgt::" + v

        all_src = sorted(src_values)
        all_tgt = sorted(tgt_values)

        nodes = []
        node_index = {}
        for v in all_src:
            nid = src_id(v)
            node_index[nid] = len(nodes)
            nodes.append({
                "id":    html.escape(nid),
                "label": html.escape(v),
                "group": 0
            })
        for v in all_tgt:
            nid = tgt_id(v)
            node_index[nid] = len(nodes)
            nodes.append({
                "id":    html.escape(nid),
                "label": html.escape(v),
                "group": 1
            })

        # Collapse parallel edges (directed for bipartite)
        edge_map = {}
        for s, t, w in raw_edges:
            key = (src_id(s), tgt_id(t))
            edge_map[key] = edge_map.get(key, 0.0) + w

        links = [
            {"source": html.escape(k[0]),
             "target": html.escape(k[1]),
             "w":      v}
            for k, v in sorted(edge_map.items())
        ]

        src_label  = html.escape(str(src_col))
        tgt_label  = html.escape(str(tgt_col))
        legend_html = (
            "<div style='display:flex;gap:18px;align-items:center;"
            "font-size:12px;color:#555;margin-bottom:4px;'>"
            "<span><span style='display:inline-block;width:12px;height:12px;"
            "border-radius:50%;background:#4e79a7;margin-right:4px;'></span>"
            + src_label +
            "</span>"
            "<span><span style='display:inline-block;width:12px;height:12px;"
            "border-radius:50%;background:#f28e2b;margin-right:4px;'></span>"
            + tgt_label +
            "</span></div>"
        )

    else:
        # Reflexive: one node set, undirected edges
        all_nodes = sorted(src_values | tgt_values)
        nodes = []
        node_index = {}
        for v in all_nodes:
            node_index[v] = len(nodes)
            nodes.append({
                "id":    html.escape(v),
                "label": html.escape(v),
                "group": 0
            })

        # Canonicalise undirected pairs
        edge_map = {}
        for s, t, w in raw_edges:
            if s == t:
                continue
            key = (min(s, t), max(s, t))
            edge_map[key] = edge_map.get(key, 0.0) + w

        links = [
            {"source": html.escape(k[0]),
             "target": html.escape(k[1]),
             "w":      v}
            for k, v in sorted(edge_map.items())
        ]
        legend_html = ""

    # ------------------------------------------------------------------ #
    # 4.  Empty-data guard                                                 #
    # ------------------------------------------------------------------ #
    if not nodes or not links:
        escaped_title = html.escape(title)
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>" + escaped_title + "</title></head><body>"
            "<p style='font-family:sans-serif;padding:2em;color:#555'>"
            "No data to display.</p></body></html>"
        )

    # ------------------------------------------------------------------ #
    # 5.  Serialise to JSON (script-safe)                                  #
    # ------------------------------------------------------------------ #
    def js_safe(x):
        return json.dumps(x).replace("</", "<\\/")

    nodes_json  = js_safe(nodes)
    links_json  = js_safe(links)
    title_json  = js_safe(html.escape(title))
    is_bip_json = js_safe(bipartite)
    val_label   = js_safe(html.escape("count" if val_col == "count" else str(val_col)))

    # ------------------------------------------------------------------ #
    # 6.  Build HTML via string concatenation (no f-strings / .format)    #
    # ------------------------------------------------------------------ #
    subtitle = (
        "Node size = degree  |  Link width = "
        + html.escape("count" if val_col == "count" else str(val_col))
    )

    html_parts = []
    html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>""")
    html_parts.append(html.escape(title))
    html_parts.append("""</title>
<style>
  body { margin:0; background:#fafafa; font-family:'Segoe UI',Arial,sans-serif; }
  #chart-wrap {
    display:flex; flex-direction:column; align-items:center;
    padding:24px 16px 32px;
  }
  h1 { font-size:18px; font-weight:600; color:#222; margin:0 0 2px; text-align:center; }
  .subtitle { font-size:12px; color:#888; margin:0 0 10px; text-align:center; }
  #legend { margin-bottom:6px; }
  #graph-svg { display:block; }
  .tooltip {
    position:fixed; pointer-events:none; background:rgba(30,30,30,.88);
    color:#fff; border-radius:5px; padding:7px 11px; font-size:12px;
    line-height:1.5; white-space:pre-wrap; max-width:260px;
    box-shadow:0 2px 8px rgba(0,0,0,.35); display:none; z-index:999;
  }
</style>
</head>
<body>
<div id="chart-wrap">
  <h1>""")
    html_parts.append(html.escape(title))
    html_parts.append("""</h1>
  <p class="subtitle">""")
    html_parts.append(subtitle)
    html_parts.append("""</p>
  <div id="legend">""")
    html_parts.append(legend_html)
    html_parts.append("""</div>
  <svg id="graph-svg"></svg>
</div>
<div class="tooltip" id="tip"></div>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
(function () {
  "use strict";

  // ── injected data ──────────────────────────────────────────────────
  const NODES     = """ + nodes_json + """;
  const LINKS     = """ + links_json + """;
  const IS_BIP    = """ + is_bip_json + """;
  const VAL_LABEL = """ + val_label + """;
  const TITLE     = """ + title_json + """;

  // ── dimensions ────────────────────────────────────────────────────
  const W = Math.min(window.innerWidth - 32, 960);
  const H = Math.max(560, Math.round(W * 0.65));

  const svg = d3.select("#graph-svg")
    .attr("width",  W)
    .attr("height", H)
    .attr("viewBox", [0, 0, W, H]);

  // defs: arrowhead (optional, not used for undirected but kept for bipartite)
  const defs = svg.append("defs");

  // ── scales ────────────────────────────────────────────────────────
  // degree map
  const degMap = new Map();
  NODES.forEach(n => degMap.set(n.id, 0));
  LINKS.forEach(l => {
    const sid = typeof l.source === "object" ? l.source.id : l.source;
    const tid = typeof l.target === "object" ? l.target.id : l.target;
    degMap.set(sid, (degMap.get(sid) || 0) + 1);
    degMap.set(tid, (degMap.get(tid) || 0) + 1);
  });

  const maxDeg = d3.max(Array.from(degMap.values())) || 1;
  const rScale = d3.scaleSqrt().domain([0, maxDeg]).range([3, 14]);

  const maxW = d3.max(LINKS, d => d.w) || 1;
  const wScale = d3.scaleSqrt().domain([0, maxW]).range([0.8, 6]);

  // colour
  const bipColour = d3.scaleOrdinal()
    .domain([0, 1])
    .range(["#4e79a7", "#f28e2b"]);

  const refColour = d3.scaleSequential()
    .domain([0, maxDeg])
    .interpolator(d3.interpolateViridis);

  function nodeColour(d) {
    if (IS_BIP) return bipColour(d.group);
    return refColour(degMap.get(d.id) || 0);
  }

  // ── seed positions on a circle (determinism) ──────────────────────
  const cx = W / 2, cy = H / 2;
  const initR = Math.min(W, H) * 0.38;
  NODES.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / NODES.length;
    n.x = cx + initR * Math.cos(angle);
    n.y = cy + initR * Math.sin(angle);
  });

  // ── simulation ────────────────────────────────────────────────────
  const sim = d3.forceSimulation(NODES)
    .force("link", d3.forceLink(LINKS)
      .id(d => d.id)
      .distance(d => {
        const sid = typeof d.source === "object" ? d.source.id : d.source;
        const tid = typeof d.target === "object" ? d.target.id : d.target;
        const avgDeg = ((degMap.get(sid) || 1) + (degMap.get(tid) || 1)) / 2;
        return Math.max(40, 120 / Math.sqrt(avgDeg));
      })
      .strength(0.4)
    )
    .force("charge", d3.forceManyBody().strength(d => {
      const deg = degMap.get(d.id) || 1;
      return -60 - deg * 4;
    }))
    .force("center", d3.forceCenter(cx, cy).strength(0.05))
    .force("collide", d3.forceCollide(d => rScale(degMap.get(d.id) || 0) + 3))
    .alphaDecay(0.03)
    .velocityDecay(0.4);

  // ── DOM elements ──────────────────────────────────────────────────
  const linkG = svg.append("g").attr("class", "links");
  const nodeG = svg.append("g").attr("class", "nodes");
  const labelG = svg.append("g").attr("class", "labels").attr("pointer-events", "none");

  const linkSel = linkG.selectAll("line")
    .data(LINKS)
    .join("line")
      .attr("stroke", "#999")
      .attr("stroke-opacity", 0.35)
      .attr("stroke-width", d => wScale(d.w));

  const nodeSel = nodeG.selectAll("circle")
    .data(NODES)
    .join("circle")
      .attr("r", d => rScale(degMap.get(d.id) || 0))
      .attr("fill", nodeColour)
      .attr("stroke", "#fff")
      .attr("stroke-width", 1.5)
      .attr("cursor", "pointer");

  // Label only top-degree nodes (top 15 % or at least 1)
  const degThreshold = d3.quantile(
    Array.from(degMap.values()).sort(d3.ascending),
    0.85
  ) || 0;

  const labelSel = labelG.selectAll("text")
    .data(NODES.filter(n => (degMap.get(n.id) || 0) >= degThreshold))
    .join("text")
      .attr("font-size", 10)
      .attr("fill", "#333")
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .text(d => d.label);

  // ── tooltip ───────────────────────────────────────────────────────
  const tip = d3.select("#tip");

  function showTip(event, html) {
    tip.style("display", "block")
       .html(html)
       .style("left", (event.clientX + 14) + "px")
       .style("top",  (event.clientY - 10) + "px");
  }
  function moveTip(event) {
    tip.style("left", (event.clientX + 14) + "px")
       .style("top",  (event.clientY - 10) + "px");
  }
  function hideTip() { tip.style("display", "none"); }

  // ── highlight helpers ─────────────────────────────────────────────
  function neighbourSet(d) {
    const s = new Set([d.id]);
    LINKS.forEach(l => {
      const sid = l.source.id || l.source;
      const tid = l.target.id || l.target;
      if (sid === d.id) s.add(tid);
      if (tid === d.id) s.add(sid);
    });
    return s;
  }

  nodeSel
    .on("mouseover", function (event, d) {
      const nbrs = neighbourSet(d);
      nodeSel.attr("opacity", n => nbrs.has(n.id) ? 1 : 0.15);
      linkSel.attr("stroke-opacity", l => {
        const sid = l.source.id || l.source;
        const tid = l.target.id || l.target;
        return (sid === d.id || tid === d.id) ? 0.8 : 0.05;
      });
      d3.select(this).attr("stroke", "#222").attr("stroke-width", 2.5);
      const deg = degMap.get(d.id) || 0;
      showTip(event,
        "<strong>" + d.label + "</strong><br>Degree: " + deg
      );
    })
    .on("mousemove", moveTip)
    .on("mouseout", function () {
      nodeSel.attr("opacity", 1);
      linkSel.attr("stroke-opacity", 0.35);
      d3.select(this).attr("stroke", "#fff").attr("stroke-width", 1.5);
      hideTip();
    });

  linkSel
    .on("mouseover", function (event, d) {
      const sid = d.source.id || d.source;
      const tid = d.target.id || d.target;
      const sLabel = (NODES.find(n => n.id === sid) || {label: sid}).label;
      const tLabel = (NODES.find(n => n.id === tid) || {label: tid}).label;
      nodeSel.attr("opacity", n => (n.id === sid || n.id === tid) ? 1 : 0.15);
      linkSel.attr("stroke-opacity", l => l === d ? 0.9 : 0.05);
      d3.select(this).attr("stroke", "#e15759").attr("stroke-opacity", 1);
      showTip(event,
        "<strong>" + sLabel + "</strong> ↔ <strong>" + tLabel + "</strong>"
        + "<br>" + VAL_LABEL + ": " + d.w
      );
    })
    .on("mousemove", moveTip)
    .on("mouseout", function () {
      nodeSel.attr("opacity", 1);
      linkSel.attr("stroke-opacity", 0.35).attr("stroke", "#999");
      hideTip();
    });

  // ── drag ──────────────────────────────────────────────────────────
  nodeSel.call(
    d3.drag()
      .on("start", (event, d) => {
        if (!event.active) sim.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
      })
      .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
      .on("end",  (event, d) => {
        if (!event.active) sim.alphaTarget(0);
        d.fx = null; d.fy = null;
      })
  );

  // ── tick ──────────────────────────────────────────────────────────
  sim.on("tick", () => {
    // Soft bounding: nudge nodes back toward the visible area
    NODES.forEach(n => {
      const r = rScale(degMap.get(n.id) || 0);
      if (isFinite(n.x)) n.x = Math.max(r, Math.min(W - r, n.x));
      if (isFinite(n.y)) n.y = Math.max(r, Math.min(H - r, n.y));
    });

    linkSel
      .attr("x1", d => d.source.x)
      .attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x)
      .attr("y2", d => d.target.y);

    nodeSel
      .attr("cx", d => d.x)
      .attr("cy", d => d.y);

    labelSel
      .attr("x", d => d.x)
      .attr("y", d => d.y - rScale(degMap.get(d.id) || 0) - 4);
  });

  // ── refit viewBox after simulation settles ────────────────────────
  sim.on("end", () => {
    try {
      const bbox = svg.node().getBBox();
      if (!isFinite(bbox.x) || !isFinite(bbox.y) ||
          !isFinite(bbox.width) || !isFinite(bbox.height) ||
          bbox.width === 0 || bbox.height === 0) return;
      const pad = 20;
      const vx = bbox.x - pad;
      const vy = bbox.y - pad;
      const vw = bbox.width  + pad * 2;
      const vh = bbox.height + pad * 2;
      svg.attr("viewBox", [vx, vy, vw, vh].join(" "))
         .attr("width",  Math.min(vw, window.innerWidth - 32))
         .attr("height", Math.min(vh, window.innerHeight - 120));
    } catch (e) { /* getBBox may throw in hidden tabs */ }
  });

})();
</script>
</body>
</html>
""")

    return "".join(html_parts)


# ------------------------------------------------------------------ #
# CLI                                                                  #
# ------------------------------------------------------------------ #
def main():
    parser = argparse.ArgumentParser(description="Force-directed graph renderer")
    parser.add_argument("--mapping", required=True, help="Path to mapping JSON file")
    parser.add_argument("--data",    required=True, help="Path to data JSON file")
    parser.add_argument("--out",     required=True, help="Path for output HTML file")
    args = parser.parse_args()

    mapping_path = pathlib.Path(args.mapping)
    data_path    = pathlib.Path(args.data)
    out_path     = pathlib.Path(args.out)

    with mapping_path.open(encoding="utf-8") as fh:
        mapping = json.load(fh)

    # Accept bare mapping or a Stage-1/2 result wrapper
    if "chart_mapping" in mapping:
        mapping = mapping["chart_mapping"]
    elif "selected_visualisation" in mapping:
        sv = mapping["selected_visualisation"]
        mapping = sv.get("encoding", sv)

    with data_path.open(encoding="utf-8") as fh:
        raw = json.load(fh)

    # Accept grouped Mondial DB or plain array
    if isinstance(raw, dict) and "tables" in raw:
        table = mapping.get("table", "")
        rows = raw["tables"].get(table, [])
    elif isinstance(raw, list):
        rows = raw
    else:
        rows = []

    html_out = render(mapping, rows)

    out_path.write_text(html_out, encoding="utf-8")
    print("Written:", out_path)


if __name__ == "__main__":
    main()