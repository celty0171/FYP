import argparse
import json
import html
import math
import pathlib


def _connected_components(n, adj):
    """Return the connected components of the graph as lists of node indices."""
    seen = [False] * n
    comps = []
    for s in range(n):
        if seen[s]:
            continue
        seen[s] = True
        stack = [s]
        comp = []
        while stack:
            u = stack.pop()
            comp.append(u)
            for v, _ in adj[u]:
                if not seen[v]:
                    seen[v] = True
                    stack.append(v)
        comps.append(comp)
    return comps


def _fiedler_order(comp, adj):
    """Spectral (Fiedler) ordering of ONE connected component.

    Order the nodes by their value in the eigenvector of the second-smallest
    eigenvalue of the component's Laplacian ``L = D - A``. That eigenvector
    minimises ``sum (x_i - x_j)^2`` over the edges, which penalises long arcs
    **super-linearly** and so makes every arc's span as short as possible (and
    reliably avoids a whole-axis "bridge" arc). Computed with deterministic
    std-lib power iteration on ``M = cI - L`` (whose top eigenvector, after the
    all-ones/eigenvalue-0 mode is projected out, is the Fiedler vector).
    """
    m = len(comp)
    if m <= 2:
        return list(comp)
    local = {node: k for k, node in enumerate(comp)}
    nbrs = [[] for _ in range(m)]
    for node in comp:
        k = local[node]
        for v, _ in adj[node]:
            if v in local:
                nbrs[k].append(local[v])
    deg = [len(nbrs[k]) for k in range(m)]
    c = 2 * max(deg) + 1  # >= largest Laplacian eigenvalue, so M is PSD

    def demean(v):
        mean = sum(v) / m
        return [vi - mean for vi in v]

    # Deterministic start (a demeaned ramp has good overlap with the Fiedler mode),
    # so the ordering is fully reproducible run to run.
    x = demean([k - (m - 1) / 2.0 for k in range(m)])
    prev_rank = None
    for _ in range(500):
        # (L x)_k = deg_k*x_k - sum_{nb} x_nb ;  M x = c*x - L x
        mx = [c * x[k] - (deg[k] * x[k] - sum(x[t] for t in nbrs[k])) for k in range(m)]
        mx = demean(mx)
        norm = math.sqrt(sum(v * v for v in mx)) or 1.0
        x = [v / norm for v in mx]
        # The induced order settles long before the vector fully converges; stop then.
        rank = sorted(range(m), key=lambda k: (x[k], k))
        if rank == prev_rank:
            break
        prev_rank = rank
    order_local = sorted(range(m), key=lambda k: (x[k], k))
    return [comp[k] for k in order_local]


def _crossing_min_order(n, edge_map, degree, names):
    """Return a 1-D node order (list of original indices) that makes every arc's
    span as short as possible — the root-cause fix for arc-diagram clutter.

    An arc diagram's clutter is governed by the linear node order on two fronts
    at once (see relationship_viz_overlap_reduction_research.md): short arcs mean
    few **crossings**, and a small **maximum** span keeps the figure compact
    (because the canvas height is set by the tallest arc, one long-range "bridge"
    arc would otherwise balloon it). So the objective is to minimise arc spans:
    both the total span ``sum|i-j|`` (minimum linear arrangement) and the maximum
    span ``max|i-j|`` (graph bandwidth). Both are NP-hard; we approximate with:

      1. **Spectral (Fiedler) seed, per connected component** — minimises
         ``sum (x_i - x_j)^2`` (long arcs penalised super-linearly), which reliably
         avoids the whole-axis bridge that a plain min-degree RCM can leave.
         Components are ordered independently (a disconnected graph has a
         degenerate global Fiedler vector) and concatenated, largest first.
      2. **Barycenter refinement** — repeatedly move each node to the weighted
         mean position of its neighbours and re-sort (ties broken by current
         position to damp oscillation). We keep whichever pass yields the lowest
         total (weighted) span, so the result never regresses below the seed.
    """
    if n <= 2:
        return list(range(n))

    adj = {i: [] for i in range(n)}
    for (i, j), w in edge_map.items():
        adj[i].append((j, w))
        adj[j].append((i, w))

    # --- 1. Spectral (Fiedler) seed, per connected component ---
    comps = _connected_components(n, adj)
    comps.sort(key=lambda c: (-len(c), min(c)))  # deterministic: largest component first
    order = []
    for comp in comps:
        order.extend(_fiedler_order(comp, adj))

    # --- 2. Barycenter refinement, keeping the shortest-total-span arrangement ---
    def arc_length(pos):
        return sum(abs(pos[i] - pos[j]) * w for (i, j), w in edge_map.items())

    pos = {node: idx for idx, node in enumerate(order)}
    best_order = list(order)
    best_cost = arc_length(pos)

    for _ in range(60):
        bary = []
        for node in range(n):
            nb = adj[node]
            if nb:
                sw = sum(w for _, w in nb)
                b = sum(pos[k] * w for k, w in nb) / sw if sw else pos[node]
            else:
                b = pos[node]
            # tie-break on current position keeps the sort stable and damps oscillation
            bary.append((b, pos[node], node))
        bary.sort()
        new_order = [node for _, _, node in bary]
        new_pos = {node: idx for idx, node in enumerate(new_order)}
        cost = arc_length(new_pos)
        if cost < best_cost:
            best_cost = cost
            best_order = list(new_order)
        if new_order == order:
            break
        order = new_order
        pos = new_pos

    return best_order


def render(mapping: dict, rows: list[dict]) -> str:
    # ------------------------------------------------------------------ #
    # 0. Read mapping fields                                               #
    # ------------------------------------------------------------------ #
    source_col = mapping["source"]
    target_col = mapping["target"]
    pattern    = mapping.get("pattern", "")
    title      = mapping.get("title", "Arc Diagram")

    # Resolve value column: support "value", legacy "width", or "count"
    value_col = mapping.get("value") or mapping.get("width") or "count"

    # Reject non-reflexive patterns explicitly
    if pattern and pattern != "reflexive_many_many_relationship":
        raise ValueError(
            "Arc diagram renderer only supports reflexive_many_many_relationship, "
            "got: " + str(pattern)
        )

    # ------------------------------------------------------------------ #
    # 1. Build node set (sorted union)                                    #
    # ------------------------------------------------------------------ #
    all_vals: set[str] = set()
    for row in rows:
        sv = row.get(source_col)
        tv = row.get(target_col)
        if sv is not None:
            all_vals.add(str(sv))
        if tv is not None:
            all_vals.add(str(tv))

    # Preliminary sorted list (will be reordered by degree later)
    prelim_names = sorted(all_vals)
    prelim_idx   = {n: i for i, n in enumerate(prelim_names)}

    # ------------------------------------------------------------------ #
    # 2. Aggregate undirected edges, drop self-loops                      #
    # ------------------------------------------------------------------ #
    edge_map: dict[tuple[int, int], float] = {}
    for row in rows:
        sv = row.get(source_col)
        tv = row.get(target_col)
        if sv is None or tv is None:
            continue
        sv, tv = str(sv), str(tv)
        if sv not in prelim_idx or tv not in prelim_idx:
            continue
        i, j = prelim_idx[sv], prelim_idx[tv]
        if i == j:
            continue  # drop self-loops
        key = (min(i, j), max(i, j))
        if value_col == "count":
            w = 1.0
        else:
            try:
                w = float(row[value_col]) if row.get(value_col) is not None else 1.0
            except (ValueError, TypeError):
                w = 1.0
        edge_map[key] = edge_map.get(key, 0.0) + w

    # ------------------------------------------------------------------ #
    # 3. Unweighted degree per node                                       #
    # ------------------------------------------------------------------ #
    degree: dict[int, int] = {i: 0 for i in range(len(prelim_names))}
    for (i, j) in edge_map:
        degree[i] = degree.get(i, 0) + 1
        degree[j] = degree.get(j, 0) + 1

    # ------------------------------------------------------------------ #
    # 4. Order axis to MINIMISE ARC CROSSINGS (not by degree)             #
    #    Ordering is the root-cause fix for arc clutter: connected nodes  #
    #    are placed adjacent so arcs stay short and local instead of long #
    #    hub-to-hub spans that cross everything. See _crossing_min_order. #
    # ------------------------------------------------------------------ #
    sorted_prelim = _crossing_min_order(
        len(prelim_names), edge_map, degree, prelim_names
    )
    # new_names[new_idx] = name
    new_names = [prelim_names[old] for old in sorted_prelim]
    # mapping old prelim index -> new axis index
    old_to_new = {old: new for new, old in enumerate(sorted_prelim)}

    n_nodes = len(new_names)

    # ------------------------------------------------------------------ #
    # 5. Remap edges to new axis indices                                  #
    # ------------------------------------------------------------------ #
    links_raw = []
    for (oi, oj), w in edge_map.items():
        ni, nj = old_to_new[oi], old_to_new[oj]
        a, b = (ni, nj) if ni < nj else (nj, ni)
        links_raw.append({"i": a, "j": b, "w": w})
    # Sort longest arcs first so short local arcs sit on top
    links_raw.sort(key=lambda l: -(l["j"] - l["i"]))

    # Per-node degree in new order
    new_deg = [degree[sorted_prelim[new]] for new in range(n_nodes)]

    # ------------------------------------------------------------------ #
    # 6. Escape all strings for safe HTML embedding                       #
    # ------------------------------------------------------------------ #
    names_escaped = [html.escape(name) for name in new_names]
    title_escaped = html.escape(title)

    if value_col == "count":
        value_label_escaped = html.escape("count")
    else:
        value_label_escaped = html.escape(str(value_col))

    source_col_escaped = html.escape(str(source_col))
    target_col_escaped = html.escape(str(target_col))

    subtitle_escaped = (
        "Arc thickness = " + value_label_escaped +
        " &middot; Node size &amp; colour = degree (# connections)" +
        " &middot; Axis ordered to minimise arc spans (spectral + barycenter)"
    )

    # ------------------------------------------------------------------ #
    # 7. Serialise for injection                                          #
    # ------------------------------------------------------------------ #
    names_json      = json.dumps(names_escaped)
    deg_json        = json.dumps(new_deg)
    links_json      = json.dumps(links_raw)
    value_label_json = json.dumps(value_label_escaped)
    n_nodes_json    = json.dumps(n_nodes)

    # ------------------------------------------------------------------ #
    # 8. Build HTML via string concatenation                              #
    # ------------------------------------------------------------------ #
    parts = []

    parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>""")
    parts.append(title_escaped)
    parts.append("""</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Segoe UI", system-ui, sans-serif;
    background: #f7f8fa;
    color: #222;
    padding: 18px;
  }
  h1 { font-size: 1.3rem; font-weight: 700; margin-bottom: 4px; }
  .subtitle {
    font-size: 0.80rem;
    color: #555;
    margin-bottom: 14px;
  }
  #chart-wrap {
    background: #fff;
    border-radius: 10px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.09);
    padding: 16px 10px;
    overflow: auto;
    display: inline-block;
    min-width: 100%;
  }
  svg { display: block; margin: 0 auto; }
  .arc-path {
    fill: none;
    stroke-linecap: round;
    transition: stroke-opacity 0.15s, stroke-width 0.15s;
  }
  .arc-path.dimmed { stroke-opacity: 0.04 !important; }
  .arc-path.highlighted { stroke-opacity: 0.92 !important; }
  .node-circle {
    stroke: #fff;
    stroke-width: 1.5px;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .node-circle.dimmed { opacity: 0.18; }
  .node-label {
    font-size: 9px;
    fill: #333;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .node-label.dimmed { opacity: 0.18; }
  .axis-line {
    stroke: #ccc;
    stroke-width: 1px;
  }
  #tooltip {
    position: fixed;
    pointer-events: none;
    background: rgba(25,25,35,0.93);
    color: #fff;
    border-radius: 7px;
    padding: 8px 13px;
    font-size: 13px;
    line-height: 1.6;
    max-width: 340px;
    z-index: 9999;
    display: none;
    box-shadow: 0 3px 14px rgba(0,0,0,0.25);
  }
</style>
</head>
<body>
<h1>""")
    parts.append(title_escaped)
    parts.append("""</h1>
<div class="subtitle">""")
    parts.append(subtitle_escaped)
    parts.append("""</div>
<div id="chart-wrap">
  <svg id="arc-svg"></svg>
</div>
<div id="tooltip"></div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
(function () {
  "use strict";

  // ---- injected data ----
  const NAMES       = """ + names_json + """;
  const DEG         = """ + deg_json + """;
  const LINKS       = """ + links_json + """;
  const N           = """ + n_nodes_json + """;
  const VALUE_LABEL = """ + value_label_json + """;

  if (N === 0) {
    document.getElementById("chart-wrap").textContent = "No data to display.";
    return;
  }

  // ---- layout constants ----
  const LEFT_PAD    = 40;
  const RIGHT_PAD   = 40;
  const TOP_PAD     = 18;
  const BOTTOM_PAD  = 24;
  const NODE_STEP   = Math.max(14, Math.min(40, Math.floor(900 / Math.max(N, 1))));
  const AXIS_WIDTH  = LEFT_PAD + (N - 1) * NODE_STEP + RIGHT_PAD;

  // x-position of node i
  function xPos(i) { return LEFT_PAD + i * NODE_STEP; }

  // Compute maxR from actual links
  let maxR = 0;
  LINKS.forEach(function (l) {
    const r = Math.abs(xPos(l.j) - xPos(l.i)) / 2;
    if (r > maxR) maxR = r;
  });

  // Estimate label space: longest label * approx char width at 9px
  const maxLabelLen = NAMES.reduce(function (m, n) { return Math.max(m, n.length); }, 0);
  const LABEL_SPACE = Math.min(maxLabelLen * 5.5 + 8, 140);

  const BASE_Y   = maxR + TOP_PAD;
  const SVG_H    = BASE_Y + LABEL_SPACE + BOTTOM_PAD;
  const SVG_W    = AXIS_WIDTH;

  // ---- scales ----
  const maxDeg = d3.max(DEG) || 1;
  const minDeg = d3.min(DEG) || 0;

  const rScale = d3.scaleSqrt()
    .domain([0, maxDeg])
    .range([2, 9]);

  const colourScale = d3.scaleSequential()
    .domain([0, maxDeg])
    .interpolator(d3.interpolateViridis);

  const maxW = d3.max(LINKS, function (l) { return l.w; }) || 1;
  const strokeScale = d3.scaleSqrt()
    .domain([0, maxW])
    .range([0.6, 5]);

  // ---- SVG ----
  const svg = d3.select("#arc-svg")
    .attr("width",  SVG_W)
    .attr("height", SVG_H);

  // ---- tooltip ----
  const tooltip = d3.select("#tooltip");
  function showTip(content) { tooltip.style("display", "block").html(content); }
  function moveTip(event) {
    tooltip
      .style("left", (event.clientX + 14) + "px")
      .style("top",  (event.clientY - 10) + "px");
  }
  function hideTip() { tooltip.style("display", "none"); }

  // ---- axis baseline ----
  svg.append("line")
    .attr("class", "axis-line")
    .attr("x1", LEFT_PAD - 10)
    .attr("y1", BASE_Y)
    .attr("x2", LEFT_PAD + (N - 1) * NODE_STEP + 10)
    .attr("y2", BASE_Y);

  // ---- arcs ----
  // Build adjacency: node -> set of neighbour indices, for highlight
  const adjSet = new Map();
  NAMES.forEach(function (_, i) { adjSet.set(i, new Set()); });
  LINKS.forEach(function (l) {
    adjSet.get(l.i).add(l.j);
    adjSet.get(l.j).add(l.i);
  });

  const arcSel = svg.append("g")
    .attr("class", "arcs")
    .selectAll("path")
    .data(LINKS)
    .join("path")
      .attr("class", "arc-path")
      .attr("d", function (l) {
        const x1 = xPos(l.i);
        const x2 = xPos(l.j);
        const r  = Math.abs(x2 - x1) / 2;
        return "M " + x1 + "," + BASE_Y +
               " A " + r + "," + r + " 0 0,1 " + x2 + "," + BASE_Y;
      })
      .attr("stroke", "#3a7abf")
      .attr("stroke-width", function (l) { return strokeScale(l.w); })
      .attr("stroke-opacity", 0.35)
      .on("mouseover", function (event, l) {
        const val = l.w.toLocaleString(undefined, { maximumFractionDigits: 2 });
        showTip(
          "<strong>" + NAMES[l.i] + "</strong>" +
          " &harr; <strong>" + NAMES[l.j] + "</strong>" +
          "<br/>" + VALUE_LABEL + ": <strong>" + val + "</strong>"
        );
        moveTip(event);
        arcSel.classed("dimmed", function (r) { return r !== l; })
              .classed("highlighted", function (r) { return r === l; });
        nodeSel.classed("dimmed", function (_, k) {
          return k !== l.i && k !== l.j;
        });
        labelSel.classed("dimmed", function (_, k) {
          return k !== l.i && k !== l.j;
        });
      })
      .on("mousemove", moveTip)
      .on("mouseout", function () {
        hideTip();
        arcSel.classed("dimmed", false).classed("highlighted", false);
        nodeSel.classed("dimmed", false);
        labelSel.classed("dimmed", false);
      });

  // ---- nodes ----
  const nodeSel = svg.append("g")
    .attr("class", "nodes")
    .selectAll("circle")
    .data(NAMES)
    .join("circle")
      .attr("class", "node-circle")
      .attr("cx", function (_, i) { return xPos(i); })
      .attr("cy", BASE_Y)
      .attr("r",  function (_, i) { return rScale(DEG[i]); })
      .attr("fill", function (_, i) { return colourScale(DEG[i]); })
      .on("mouseover", function (event, name) {
        const i = NAMES.indexOf(name);
        const deg = DEG[i];
        showTip(
          "<strong>" + name + "</strong>" +
          "<br/>Degree: <strong>" + deg + "</strong>"
        );
        moveTip(event);
        const nbrs = adjSet.get(i);
        arcSel.classed("dimmed", function (l) {
          return l.i !== i && l.j !== i;
        }).classed("highlighted", false);
        nodeSel.classed("dimmed", function (_, k) {
          return k !== i && !nbrs.has(k);
        });
        labelSel.classed("dimmed", function (_, k) {
          return k !== i && !nbrs.has(k);
        });
      })
      .on("mousemove", moveTip)
      .on("mouseout", function () {
        hideTip();
        arcSel.classed("dimmed", false).classed("highlighted", false);
        nodeSel.classed("dimmed", false);
        labelSel.classed("dimmed", false);
      });

  // ---- labels ----
  // Thin labels when nodes are dense: show every k-th or degree >= threshold
  let labelStep = 1;
  if (N > 80)  labelStep = 4;
  else if (N > 40) labelStep = 2;

  const degThreshold = (N > 60) ? Math.ceil(maxDeg * 0.15) : 0;

  const labelSel = svg.append("g")
    .attr("class", "labels")
    .selectAll("text")
    .data(NAMES)
    .join("text")
      .attr("class", "node-label")
      .attr("x", function (_, i) { return xPos(i); })
      .attr("y", BASE_Y + 4)
      .attr("transform", function (_, i) {
        const x = xPos(i);
        return "rotate(90," + x + "," + (BASE_Y + 4) + ")";
      })
      .attr("text-anchor", "start")
      .attr("display", function (_, i) {
        if (DEG[i] >= degThreshold && i % labelStep === 0) return null;
        if (DEG[i] > degThreshold) return null;
        return "none";
      })
      .text(function (d) { return d; });

  // ---- BBox refit ----
  // After all marks are drawn, refit the SVG to its actual content
  try {
    const bbox = svg.node().getBBox();
    const pad  = 10;
    svg
      .attr("viewBox",
        (bbox.x - pad) + " " + (bbox.y - pad) + " " +
        (bbox.width + 2 * pad) + " " + (bbox.height + 2 * pad)
      )
      .attr("width",  bbox.width  + 2 * pad)
      .attr("height", bbox.height + 2 * pad);
  } catch (e) {
    // getBBox may fail in non-browser environments; ignore
  }

})();
</script>
</body>
</html>""")

    return "".join(parts)


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="Arc diagram renderer")
    parser.add_argument("--mapping", required=True, help="Path to mapping JSON file")
    parser.add_argument("--data",    required=True, help="Path to data JSON file")
    parser.add_argument("--out",     required=True, help="Path to output HTML file")
    args = parser.parse_args()

    mapping_path = pathlib.Path(args.mapping)
    data_path    = pathlib.Path(args.data)
    out_path     = pathlib.Path(args.out)

    with mapping_path.open(encoding="utf-8") as f:
        mapping = json.load(f)

    # Accept Stage-1/2 result objects
    if "chart_mapping" in mapping:
        mapping = mapping["chart_mapping"]
    elif "selected_visualisation" in mapping:
        sv = mapping["selected_visualisation"]
        mapping = sv.get("encoding", sv)

    with data_path.open(encoding="utf-8") as f:
        raw_data = json.load(f)

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