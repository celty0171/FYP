import argparse
import json
import html
import pathlib


def _fenwick_crossings(pairs, t_size):
    """Count link crossings of a two-layer (bipartite) drawing in O(E log |T|).

    ``pairs`` are the links as ``(source_rank, target_rank)``. Two links cross iff
    their endpoints invert between the layers; sorting the pairs ascending by
    ``(source_rank, target_rank)`` and counting inversions in the target ranks via
    a Fenwick/BIT gives the crossing number exactly (equal-source links sit in
    ascending target order, so they are correctly never counted as a crossing).
    """
    pairs = sorted(pairs)
    tree = [0] * (t_size + 2)
    cross = 0
    seen = 0
    for _, t in pairs:
        # crossings with already-placed links whose target rank is > t
        i = t + 1
        le = 0
        while i > 0:
            le += tree[i]
            i -= i & -i
        cross += seen - le
        i = t + 1
        while i <= t_size + 1:
            tree[i] += 1
            i += i & -i
        seen += 1
    return cross


def _order_bipartite(all_sources, all_targets, link_map, sweeps=16):
    """Order the two layers of a Sankey to minimise link crossings.

    A Sankey is a layered (Sugiyama) drawing; with the layers fixed, clutter is the
    number of link crossings, governed by the *within-layer* node order. A single
    forward pass under-orders a dense graph. We instead run the classic **iterated
    two-layer barycenter** sweep: repeatedly place each source at the weighted-mean
    rank of its targets and each target at the weighted-mean rank of its sources,
    re-sorting after each half-sweep. Barycenter is seed-sensitive (local optima),
    so we try two deterministic seeds (alphabetical, and by descending incident
    weight) and keep whichever arrangement has the fewest crossings.
    """
    s_nb = {s: [] for s in all_sources}
    t_nb = {t: [] for t in all_targets}
    for (s, t), w in link_map.items():
        if w > 0:
            s_nb[s].append((t, w))
            t_nb[t].append((s, w))

    def order_by(nodes, nb, rank_other):
        return sorted(nodes, key=lambda x: (
            (sum(rank_other[y] * w for y, w in nb[x]) / sum(w for _, w in nb[x]))
            if nb[x] else 0.0, x))

    links = [(s, t) for (s, t), w in link_map.items() if w > 0]
    seeds = [
        sorted(all_targets),  # alphabetical
        sorted(all_targets, key=lambda t: (-sum(w for _, w in t_nb[t]), t)),  # heaviest first
    ]
    best = None
    best_cost = None
    for seed in seeds:
        tgts = list(seed)
        srcs = list(all_sources)
        trank = {t: i for i, t in enumerate(tgts)}
        for _ in range(sweeps):
            srcs = order_by(srcs, s_nb, trank)
            srank = {s: i for i, s in enumerate(srcs)}
            tgts = order_by(tgts, t_nb, srank)
            trank = {t: i for i, t in enumerate(tgts)}
            pairs = [(srank[s], trank[t]) for (s, t) in links]
            c = _fenwick_crossings(pairs, len(tgts))
            if best_cost is None or c < best_cost:
                best_cost = c
                best = (list(srcs), list(tgts))
    if best is None:
        return sorted(all_sources), sorted(all_targets)
    return best


def render(mapping: dict, rows: list[dict]) -> str:
    source_col = mapping["source"]
    target_col = mapping["target"]
    width_col = mapping["width"]
    title = mapping.get("title", "Sankey Diagram")
    pattern = mapping.get("pattern", "")

    # ------------------------------------------------------------------ #
    # 1. Aggregate links: sum width for duplicate (source, target) pairs  #
    # ------------------------------------------------------------------ #
    link_map = {}
    for row in rows:
        src_val = str(row[source_col]) if row.get(source_col) is not None else ""
        tgt_val = str(row[target_col]) if row.get(target_col) is not None else ""
        try:
            w = float(row[width_col]) if row.get(width_col) is not None else 0.0
        except (ValueError, TypeError):
            w = 0.0
        key = (src_val, tgt_val)
        link_map[key] = link_map.get(key, 0.0) + w

    # Remove zero-weight links
    link_map = {k: v for k, v in link_map.items() if v > 0}

    # Collect unique sources and targets
    all_sources = sorted({k[0] for k in link_map})
    all_targets = sorted({k[1] for k in link_map})

    # ------------------------------------------------------------------ #
    # 2. Ordering: minimise link crossings                                #
    #    Iterated two-layer barycenter (Sugiyama) — a single forward pass  #
    #    under-orders a dense graph, so we sweep both layers to            #
    #    convergence and keep the arrangement with the fewest crossings.   #
    # ------------------------------------------------------------------ #
    ordered_sources, ordered_targets = _order_bipartite(
        all_sources, all_targets, link_map
    )

    tgt_rank = {t: i for i, t in enumerate(ordered_targets)}
    src_rank = {s: i for i, s in enumerate(ordered_sources)}

    # ------------------------------------------------------------------ #
    # 3. Build nodes and links for D3-Sankey                             #
    # ------------------------------------------------------------------ #
    nodes = []
    for s in ordered_sources:
        nodes.append({
            "name": "src:" + s,
            "label": html.escape(s),
            "side": "source",
            "order": src_rank[s]
        })
    for t in ordered_targets:
        nodes.append({
            "name": "tgt:" + t,
            "label": html.escape(t),
            "side": "target",
            "order": tgt_rank[t]
        })

    # Step C — build links ordered by target rank then source rank
    raw_links = []
    for (src, tgt), w in link_map.items():
        raw_links.append({
            "source": "src:" + src,
            "target": "tgt:" + tgt,
            "value": w,
            "sourceLabel": html.escape(src),
            "targetLabel": html.escape(tgt),
            "targetOrder": tgt_rank.get(tgt, 0),
            "sourceOrder": src_rank.get(src, 0)
        })

    raw_links.sort(key=lambda l: (l["targetOrder"], l["sourceOrder"]))

    # Compute subtitle
    if pattern == "reflexive_many_many_relationship":
        subtitle = (
            "Flow width = " + html.escape(str(width_col)) +
            " \u00b7 Same entity set on both sides (directed self-flow)"
        )
    else:
        subtitle = (
            "Flow width = " + html.escape(str(width_col)) +
            " \u00b7 " + html.escape(str(source_col)) +
            " \u2192 " + html.escape(str(target_col))
        )

    # ------------------------------------------------------------------ #
    # 4. Compute canvas size                                              #
    # ------------------------------------------------------------------ #
    n_src = len(ordered_sources)
    n_tgt = len(ordered_targets)
    max_nodes = max(n_src, n_tgt, 1)
    node_padding = 14
    node_height_min = 28
    svg_height = max(600, max_nodes * (node_height_min + node_padding) + 120)
    svg_width = max(960, 200 + 60 * max(
        max((len(s) for s in ordered_sources), default=0),
        max((len(t) for t in ordered_targets), default=0)
    ))
    svg_width = min(svg_width, 1400)

    # ------------------------------------------------------------------ #
    # 5. Serialise data for injection                                     #
    # ------------------------------------------------------------------ #
    nodes_json = json.dumps(nodes)
    links_json = json.dumps(raw_links)
    title_escaped = html.escape(title)
    subtitle_escaped = html.escape(subtitle)
    width_col_escaped = html.escape(str(width_col))

    # ------------------------------------------------------------------ #
    # 6. Build HTML via string concatenation (no f-strings / .format)    #
    # ------------------------------------------------------------------ #
    html_parts = []

    html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>""")
    html_parts.append(title_escaped)
    html_parts.append("""</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Segoe UI", system-ui, sans-serif;
    background: #f7f8fa;
    color: #222;
    padding: 18px;
  }
  h1 { font-size: 1.35rem; font-weight: 700; margin-bottom: 4px; }
  .subtitle {
    font-size: 0.82rem;
    color: #555;
    margin-bottom: 16px;
    letter-spacing: 0.01em;
  }
  #chart-wrap {
    background: #fff;
    border-radius: 10px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.09);
    padding: 20px 10px 20px 10px;
    overflow-x: auto;
  }
  svg { display: block; margin: 0 auto; }
  .node rect {
    stroke: #fff;
    stroke-width: 1.5px;
    rx: 3px;
    cursor: pointer;
  }
  .node text {
    font-size: 12px;
    fill: #222;
    pointer-events: none;
    dominant-baseline: middle;
  }
  .link {
    fill: none;
    stroke-opacity: 0.42;
    cursor: pointer;
    transition: stroke-opacity 0.15s;
  }
  .link.dimmed { stroke-opacity: 0.06; }
  .link.highlighted { stroke-opacity: 0.72; }
  .node.dimmed rect { opacity: 0.25; }
  .node.dimmed text { opacity: 0.25; }
  #tooltip {
    position: fixed;
    pointer-events: none;
    background: rgba(30,30,40,0.93);
    color: #fff;
    border-radius: 7px;
    padding: 8px 13px;
    font-size: 13px;
    line-height: 1.55;
    max-width: 320px;
    z-index: 9999;
    display: none;
    box-shadow: 0 3px 14px rgba(0,0,0,0.25);
  }
  .legend {
    margin-top: 14px;
    display: flex;
    flex-wrap: wrap;
    gap: 10px 22px;
    font-size: 12px;
    color: #444;
    padding-left: 8px;
  }
  .legend-item { display: flex; align-items: center; gap: 6px; }
  .legend-swatch {
    width: 18px; height: 12px; border-radius: 3px; flex-shrink: 0;
  }
</style>
</head>
<body>
<h1>""")
    html_parts.append(title_escaped)
    html_parts.append("""</h1>
<div class="subtitle">""")
    html_parts.append(subtitle_escaped)
    html_parts.append("""</div>
<div id="chart-wrap">
  <svg id="sankey-svg"></svg>
  <div class="legend" id="legend"></div>
</div>
<div id="tooltip"></div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12/dist/d3-sankey.min.js"></script>
<script>
(function () {
  "use strict";

  // ---- injected data ----
  const RAW_NODES = """ + nodes_json + """;
  const RAW_LINKS = """ + links_json + """;
  const WIDTH_COL  = """ + json.dumps(width_col_escaped) + """;
  const SVG_W      = """ + str(svg_width) + """;
  const SVG_H      = """ + str(svg_height) + """;

  // ---- layout constants ----
  const MARGIN     = { top: 18, right: 180, bottom: 18, left: 180 };
  const NODE_W     = 18;
  const NODE_PAD   = """ + str(node_padding) + """;
  const ITERATIONS = 64;

  // ---- colour scale: one colour per target node ----
  const targetLabels = RAW_NODES
    .filter(d => d.side === "target")
    .map(d => d.label);
  const colourScale = d3.scaleOrdinal()
    .domain(targetLabels)
    .range(d3.schemeTableau10.concat(d3.schemePastel1));

  function linkColour(d) {
    // colour by target label
    const tLabel = d.targetLabel || (d.target && d.target.label) || "";
    return colourScale(tLabel);
  }

  // ---- build SVG ----
  const svg = d3.select("#sankey-svg")
    .attr("width",  SVG_W)
    .attr("height", SVG_H);

  const g = svg.append("g");

  // ---- tooltip ----
  const tooltip = d3.select("#tooltip");

  function showTip(html) { tooltip.style("display", "block").html(html); }
  function moveTip(event) {
    const tx = event.clientX + 14;
    const ty = event.clientY - 10;
    tooltip.style("left", tx + "px").style("top", ty + "px");
  }
  function hideTip() { tooltip.style("display", "none"); }

  // ---- sankey layout ----
  const sankeyGen = d3.sankey()
    .nodeId(d => d.name)
    .nodeWidth(NODE_W)
    .nodePadding(NODE_PAD)
    .nodeAlign(d3.sankeyLeft)
    .nodeSort((a, b) => d3.ascending(a.order, b.order))
    .linkSort((a, b) =>
      (a.target.order - b.target.order) ||
      (a.source.order - b.source.order)
    )
    .iterations(ITERATIONS)
    .extent([
      [MARGIN.left, MARGIN.top],
      [SVG_W - MARGIN.right, SVG_H - MARGIN.bottom]
    ]);

  // Deep-clone so d3-sankey can mutate freely
  const graphData = sankeyGen({
    nodes: RAW_NODES.map(d => Object.assign({}, d)),
    links: RAW_LINKS.map(d => Object.assign({}, d))
  });

  const { nodes, links } = graphData;

  // ---- draw links (ascending weight so thin links are on top) ----
  const linksSorted = links.slice().sort((a, b) => b.value - a.value);

  const linkSel = g.append("g")
    .attr("class", "links")
    .selectAll("path")
    .data(linksSorted)
    .join("path")
      .attr("class", "link")
      .attr("d", d3.sankeyLinkHorizontal())
      .attr("stroke", d => linkColour(d))
      .attr("stroke-width", d => Math.max(1, d.width))
      .on("mouseover", function (event, d) {
        const srcLabel = d.source.label || d.source.name;
        const tgtLabel = d.target.label || d.target.name;
        const val = d.value.toLocaleString(undefined, { maximumFractionDigits: 2 });
        showTip(
          "<strong>" + srcLabel + "</strong>" +
          " &rarr; <strong>" + tgtLabel + "</strong>" +
          "<br/>" + WIDTH_COL + ": <strong>" + val + "</strong>"
        );
        moveTip(event);
        linkSel.classed("dimmed", l => l !== d)
               .classed("highlighted", l => l === d);
      })
      .on("mousemove", moveTip)
      .on("mouseout", function () {
        hideTip();
        linkSel.classed("dimmed", false).classed("highlighted", false);
        nodeSel.classed("dimmed", false);
      });

  // ---- draw nodes ----
  const nodeSel = g.append("g")
    .attr("class", "nodes")
    .selectAll("g")
    .data(nodes)
    .join("g")
      .attr("class", "node");

  nodeSel.append("rect")
    .attr("x", d => d.x0)
    .attr("y", d => d.y0)
    .attr("width",  d => d.x1 - d.x0)
    .attr("height", d => Math.max(1, d.y1 - d.y0))
    .attr("fill", d => {
      if (d.side === "target") return colourScale(d.label);
      // source nodes: blend of connected target colours
      const conns = links.filter(l => l.source === d);
      if (conns.length === 0) return "#aaa";
      if (conns.length === 1) return colourScale(conns[0].target.label);
      return "#607d8b";
    })
    .attr("rx", 3);

  // Labels: right of rect for source nodes, left of rect for target nodes
  nodeSel.append("text")
    .attr("x", d => d.side === "source" ? d.x1 + 7 : d.x0 - 7)
    .attr("y", d => (d.y0 + d.y1) / 2)
    .attr("text-anchor", d => d.side === "source" ? "start" : "end")
    .text(d => d.label);

  // Node interaction
  nodeSel
    .on("mouseover", function (event, d) {
      const total = d.value !== undefined
        ? d.value.toLocaleString(undefined, { maximumFractionDigits: 2 })
        : "–";
      showTip(
        "<strong>" + (d.label || d.name) + "</strong>" +
        "<br/>Total flow: <strong>" + total + "</strong>"
      );
      moveTip(event);

      // Highlight connected links; dim others and unconnected nodes
      const connectedLinks = new Set(
        links.filter(l => l.source === d || l.target === d)
      );
      const connectedNodes = new Set();
      connectedLinks.forEach(l => {
        connectedNodes.add(l.source);
        connectedNodes.add(l.target);
      });

      linkSel
        .classed("highlighted", l => connectedLinks.has(l))
        .classed("dimmed",      l => !connectedLinks.has(l));

      nodeSel
        .classed("dimmed", n => !connectedNodes.has(n) && n !== d);
    })
    .on("mousemove", moveTip)
    .on("mouseout", function () {
      hideTip();
      linkSel.classed("dimmed", false).classed("highlighted", false);
      nodeSel.classed("dimmed", false);
    });

  // ---- legend for target colours ----
  const legendEl = document.getElementById("legend");
  targetLabels.forEach(lbl => {
    const item = document.createElement("div");
    item.className = "legend-item";
    const swatch = document.createElement("div");
    swatch.className = "legend-swatch";
    swatch.style.background = colourScale(lbl);
    const span = document.createElement("span");
    span.textContent = lbl;
    item.appendChild(swatch);
    item.appendChild(span);
    legendEl.appendChild(item);
  });

})();
</script>
</body>
</html>""")

    return "".join(html_parts)


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="Sankey diagram renderer")
    parser.add_argument("--mapping", required=True, help="Path to mapping JSON file")
    parser.add_argument("--data",    required=True, help="Path to data JSON file")
    parser.add_argument("--out",     required=True, help="Path to output HTML file")
    args = parser.parse_args()

    mapping_path = pathlib.Path(args.mapping)
    data_path    = pathlib.Path(args.data)
    out_path     = pathlib.Path(args.out)

    with mapping_path.open(encoding="utf-8") as f:
        mapping = json.load(f)

    # Accept either a bare mapping or a Stage-1/2 result object
    if "chart_mapping" in mapping:
        mapping = mapping["chart_mapping"]
    elif "selected_visualisation" in mapping:
        sv = mapping["selected_visualisation"]
        mapping = sv.get("encoding", sv)

    with data_path.open(encoding="utf-8") as f:
        raw_data = json.load(f)

    # Accept either a grouped Mondial DB or a plain array
    if isinstance(raw_data, dict) and "tables" in raw_data:
        table_name = mapping["table"]
        rows = raw_data["tables"][table_name]
    elif isinstance(raw_data, list):
        rows = raw_data
    else:
        raise ValueError(
            "Data file must be a JSON array or a grouped Mondial DB "
            "({'tables': {...}})"
        )

    html_out = render(mapping, rows)
    out_path.write_text(html_out, encoding="utf-8")
    print("Written:", out_path)


if __name__ == "__main__":
    main()