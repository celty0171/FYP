import argparse
import html
import json
import math
import pathlib
import sys


# ---------------------------------------------------------------------------
# Spectral / Fiedler ordering helpers (pure Python, std-lib only)
# ---------------------------------------------------------------------------

def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _norm(v):
    n = math.sqrt(_dot(v, v))
    return n


def _normalise(v):
    n = _norm(v)
    if n == 0:
        return v[:]
    return [x / n for x in v]


def _demean(v):
    mu = sum(v) / len(v)
    return [x - mu for x in v]


def _matvec_laplacian_shift(adj, deg, c, v):
    """Compute (cI - L) * v  =  c*v - L*v  =  c*v - (D - A)*v."""
    n = len(v)
    result = [c * v[i] - deg[i] * v[i] for i in range(n)]
    for i, neighbours in enumerate(adj):
        for j, w in neighbours:
            result[i] += w * v[j]
    return result


def _fiedler_order(nodes, edges):
    """
    Return a list of node indices ordered by the Fiedler vector
    (eigenvector of the second-smallest eigenvalue of the Laplacian).
    Works per connected component; concatenates components.
    edges: list of (i, j, w) with i < j, all indices in [0, n).
    """
    n = len(nodes)
    if n == 0:
        return []
    if n == 1:
        return [0]

    # Build adjacency list (weighted) and degree vector
    adj = [[] for _ in range(n)]
    deg = [0.0] * n
    for i, j, w in edges:
        adj[i].append((j, w))
        adj[j].append((i, w))
        deg[i] += w
        deg[j] += w

    # Find connected components via BFS
    visited = [-1] * n
    components = []
    for start in range(n):
        if visited[start] != -1:
            continue
        comp = []
        queue = [start]
        visited[start] = len(components)
        head = 0
        while head < len(queue):
            u = queue[head]; head += 1
            comp.append(u)
            for v, _ in adj[u]:
                if visited[v] == -1:
                    visited[v] = len(components)
                    queue.append(v)
        components.append(comp)

    order = []
    for comp in components:
        if len(comp) == 1:
            order.extend(comp)
            continue
        if len(comp) == 2:
            order.extend(comp)
            continue

        # Sub-problem: Fiedler vector for this component
        nc = len(comp)
        idx = {v: k for k, v in enumerate(comp)}

        sub_adj = [[] for _ in range(nc)]
        sub_deg = [0.0] * nc
        for gi in comp:
            for gj, w in adj[gi]:
                li, lj = idx[gi], idx[gj]
                sub_adj[li].append((lj, w))
                sub_deg[li] += w  # already double-counted but symmetric

        # c >= largest eigenvalue of L; use 2*max_deg + 1
        max_deg = max(sub_deg)
        c = 2.0 * max_deg + 1.0

        # Power iteration on (cI - L) to find Fiedler vector
        # Start with a random-ish but deterministic vector
        import hashlib
        seed_bytes = hashlib.md5(str(comp).encode()).digest()
        seed_val = int.from_bytes(seed_bytes[:4], 'little')
        v = [(((seed_val >> k) & 1) * 2 - 1) * (k + 1) for k in range(nc)]
        v = _normalise(_demean(v))

        for _ in range(200):
            v_new = _matvec_laplacian_shift(sub_adj, sub_deg, c, v)
            v_new = _normalise(_demean(v_new))
            if _norm([v_new[k] - v[k] for k in range(nc)]) < 1e-9:
                break
            v = v_new

        # Sort component nodes by Fiedler value
        comp_order = sorted(range(nc), key=lambda k: v[k])
        order.extend(comp[k] for k in comp_order)

    return order


def _barycenter_refine(order, edges, names, n_passes=60):
    """
    Barycenter iteration: repeatedly move each node to the mean position
    of its neighbours and re-sort.  Tie-break on current position (not id).
    Returns the permutation (list of original node indices) with the
    lowest total weighted span.
    """
    n = len(order)
    if n <= 2:
        return order[:]

    # Build adjacency: node -> list of (neighbour_original_idx, weight)
    adj = [[] for _ in range(n)]
    for i, j, w in edges:
        adj[i].append((j, w))
        adj[j].append((i, w))

    def total_span(perm):
        pos = [0] * n
        for rank, node in enumerate(perm):
            pos[node] = rank
        return sum(w * abs(pos[i] - pos[j]) for i, j, w in edges)

    best = order[:]
    best_span = total_span(best)
    current = order[:]

    for _ in range(n_passes):
        pos = [0] * n
        for rank, node in enumerate(current):
            pos[node] = rank

        bary = []
        for node in range(n):
            nbrs = adj[node]
            if nbrs:
                total_w = sum(w for _, w in nbrs)
                if total_w > 0:
                    bc = sum(w * pos[nb] for nb, w in nbrs) / total_w
                else:
                    bc = float(pos[node])
            else:
                bc = float(pos[node])
            bary.append((bc, pos[node], node))  # tie-break on current pos

        bary.sort()
        current = [t[2] for t in bary]

        sp = total_span(current)
        if sp < best_span:
            best_span = sp
            best = current[:]

    return best


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render(mapping: dict, rows: list) -> str:
    # ---- Read mapping fields -----------------------------------------------
    pattern = mapping.get("pattern", "")
    if pattern and pattern != "reflexive_many_many_relationship":
        raise ValueError(
            "arc_diagram renderer only supports reflexive_many_many_relationship, "
            "got: " + str(pattern)
        )

    src_col = mapping["source"]
    tgt_col = mapping["target"]
    val_col = mapping.get("value", mapping.get("width", "count"))
    title   = mapping.get("title", "Arc Diagram")

    # ---- Graceful empty-data handling --------------------------------------
    if not rows:
        return _no_data_html(html.escape(title))

    # ---- Build node set ----------------------------------------------------
    node_set = set()
    for row in rows:
        s = row.get(src_col)
        t = row.get(tgt_col)
        if s is not None:
            node_set.add(str(s))
        if t is not None:
            node_set.add(str(t))

    if not node_set:
        return _no_data_html(html.escape(title))

    names_raw = sorted(node_set)          # initial alphabetical sort (will be reordered)
    name_to_idx = {name: i for i, name in enumerate(names_raw)}
    n = len(names_raw)

    # ---- Aggregate undirected edges ----------------------------------------
    edge_map = {}   # (min_idx, max_idx) -> weight
    for row in rows:
        s = row.get(src_col)
        t = row.get(tgt_col)
        if s is None or t is None:
            continue
        si = name_to_idx.get(str(s))
        ti = name_to_idx.get(str(t))
        if si is None or ti is None:
            continue
        if si == ti:
            continue  # drop self-loops
        key = (min(si, ti), max(si, ti))
        if val_col == "count":
            w = 1.0
        else:
            raw_w = row.get(val_col)
            try:
                w = float(raw_w) if raw_w is not None else 1.0
            except (TypeError, ValueError):
                w = 1.0
        edge_map[key] = edge_map.get(key, 0.0) + w

    if not edge_map:
        return _no_data_html(html.escape(title))

    edges_raw = [(i, j, w) for (i, j), w in edge_map.items()]

    # ---- Compute unweighted degree (connectivity count) --------------------
    deg_raw = [0] * n
    for i, j, _ in edges_raw:
        deg_raw[i] += 1
        deg_raw[j] += 1

    # ---- Axis ordering: Fiedler seed + barycenter refinement ---------------
    fiedler_order = _fiedler_order(list(range(n)), edges_raw)
    best_order    = _barycenter_refine(fiedler_order, edges_raw, names_raw, n_passes=60)

    # best_order[rank] = original node index
    # Build rank lookup: original_idx -> rank
    rank_of = [0] * n
    for rank, orig in enumerate(best_order):
        rank_of[orig] = rank

    # Reorder names and degrees into axis order
    names_ordered = [names_raw[best_order[r]] for r in range(n)]
    deg_ordered   = [deg_raw[best_order[r]]   for r in range(n)]

    # Remap edges to axis indices
    links = []
    for i, j, w in edges_raw:
        ri = rank_of[i]
        rj = rank_of[j]
        links.append({"i": min(ri, rj), "j": max(ri, rj), "w": w})

    # Sort links longest-first so short local arcs render on top
    links.sort(key=lambda lk: lk["j"] - lk["i"], reverse=True)

    # ---- Escape all string data before embedding ---------------------------
    names_escaped = [html.escape(nm) for nm in names_ordered]

    # ---- Determine subtitle ------------------------------------------------
    if val_col == "count":
        arc_enc = "Arc thickness: edge count"
    else:
        arc_enc = "Arc thickness: " + html.escape(str(val_col))
    subtitle = arc_enc + " · Node size &amp; colour: degree"

    # ---- Serialise to JSON (script-safe) -----------------------------------
    def safe_json(obj):
        return json.dumps(obj).replace("</", "<\\/")

    names_json = safe_json(names_escaped)
    deg_json   = safe_json(deg_ordered)
    links_json = safe_json(links)
    title_js   = safe_json(html.escape(title))
    subtitle_js = safe_json(subtitle)

    # ---- Build HTML via string concatenation (no f-strings / .format) ------
    html_parts = []
    html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>""")
    html_parts.append(html.escape(title))
    html_parts.append("""</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f8f9fa;
    color: #222;
    padding: 24px 16px 40px;
  }
  #chart-container {
    text-align: center;
  }
  svg {
    display: block;
    margin: 0 auto;
    background: #fff;
    border-radius: 6px;
    box-shadow: 0 1px 6px rgba(0,0,0,.10);
    overflow: visible;
  }
  #tooltip {
    position: absolute;
    pointer-events: none;
    background: rgba(30,30,40,.88);
    color: #fff;
    border-radius: 5px;
    padding: 7px 11px;
    font-size: 12px;
    line-height: 1.5;
    max-width: 260px;
    white-space: pre-wrap;
    opacity: 0;
    transition: opacity .12s;
    z-index: 999;
  }
</style>
</head>
<body>
<div id="chart-container"></div>
<div id="tooltip"></div>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
(function() {
  "use strict";

  // ── Embedded data ─────────────────────────────────────────────────────────
  const NAMES    = """ + names_json + """;
  const DEG      = """ + deg_json + """;
  const LINKS    = """ + links_json + """;
  const TITLE    = """ + title_js + """;
  const SUBTITLE = """ + subtitle_js + """;

  const n = NAMES.length;

  // ── Guard: nothing to draw ────────────────────────────────────────────────
  if (n === 0 || LINKS.length === 0) {
    document.getElementById("chart-container").innerHTML =
      "<p style='padding:2em;color:#666'>No data to display.</p>";
    return;
  }

  // ── Layout constants ──────────────────────────────────────────────────────
  const NODE_SPACING  = 28;          // px between adjacent nodes
  const LEFT_PAD      = 60;
  const RIGHT_PAD     = 60;
  const TOP_PAD       = 18;
  const BOTTOM_PAD    = 20;
  const FONT_SIZE     = 9;
  const AXIS_STROKE   = 0.5;

  // ── X scale ───────────────────────────────────────────────────────────────
  const axisWidth = (n - 1) * NODE_SPACING;
  const xOf = function(rank) { return LEFT_PAD + rank * NODE_SPACING; };

  // ── Arc heights: compute raw radii, then cap ──────────────────────────────
  const rawR = LINKS.map(function(lk) {
    return Math.abs(xOf(lk.j) - xOf(lk.i)) / 2;
  });

  // 95th-percentile cap: keep figure compact even if one bridge arc exists
  const sortedR = rawR.slice().sort(function(a, b) { return a - b; });
  const p95idx  = Math.floor(sortedR.length * 0.95);
  const p95R    = sortedR[Math.max(0, p95idx - 1)] || sortedR[sortedR.length - 1] || 1;
  // Cap = max(p95R * 1.6, 120) but never more than axisWidth * 0.45
  const capR    = Math.min(Math.max(p95R * 1.6, 120), axisWidth * 0.45 + 1);
  const maxR    = Math.min(Math.max.apply(null, rawR.concat([1])), capR);

  // ── Longest label → label space ───────────────────────────────────────────
  // Decide which labels to show (thin when dense)
  const labelStep = n > 80 ? 5 : n > 40 ? 3 : n > 20 ? 2 : 1;
  const shownLabels = NAMES.filter(function(_, i) { return i % labelStep === 0; });
  const maxLabelLen = shownLabels.reduce(function(mx, nm) {
    return Math.max(mx, nm.length);
  }, 0);
  const labelSpace = maxLabelLen * FONT_SIZE * 0.62 + 12;

  // ── Two-sided arcs: alternate above/below the baseline to halve visual density ──
  // Alternate by draw order (longest-first), so tall arcs are split between the two sides.
  const sideOf = LINKS.map(function(_, k) { return (k % 2 === 0) ? 1 : -1; });
  let topMaxR = 1, botMaxR = 1;
  LINKS.forEach(function(lk, k) {
    const r = Math.min(Math.abs(xOf(lk.j) - xOf(lk.i)) / 2, capR);
    if (sideOf[k] > 0) { if (r > topMaxR) topMaxR = r; }
    else { if (r > botMaxR) botMaxR = r; }
  });

  // ── SVG dimensions ────────────────────────────────────────────────────────
  const baseY    = topMaxR + TOP_PAD;
  const svgW     = axisWidth + LEFT_PAD + RIGHT_PAD;
  const svgH     = baseY + botMaxR + labelSpace + BOTTOM_PAD;
  const labelY   = baseY + botMaxR + 4;   // labels sit below the bottom-side arcs

  // ── Scales ────────────────────────────────────────────────────────────────
  const maxDeg   = Math.max.apply(null, DEG.concat([1]));
  const minDeg   = Math.min.apply(null, DEG.concat([0]));
  const rScale   = d3.scaleSqrt().domain([0, maxDeg]).range([2, 10]);
  const colScale = d3.scaleSequential(d3.interpolateViridis).domain([0, maxDeg]);

  const maxW     = Math.max.apply(null, LINKS.map(function(lk) { return lk.w; }).concat([1]));
  const minW     = Math.min.apply(null, LINKS.map(function(lk) { return lk.w; }).concat([0]));
  const swScale  = d3.scaleSqrt().domain([0, maxW]).range([0.8, 5]);

  // Single-hue arc colour: mid-dark muted blue; optionally ramp on w
  // We use a single fixed hue (#4477aa) at varying opacity for clarity.
  const ARC_COLOR = "#4477aa";

  // ── SVG root ──────────────────────────────────────────────────────────────
  const container = d3.select("#chart-container");

  // Title + subtitle
  container.append("div")
    .style("font-size", "17px")
    .style("font-weight", "600")
    .style("margin-bottom", "4px")
    .style("color", "#1a1a2e")
    .text(TITLE);

  container.append("div")
    .style("font-size", "11px")
    .style("color", "#666")
    .style("margin-bottom", "14px")
    .html(SUBTITLE);

  const svg = container.append("svg")
    .attr("width",  svgW)
    .attr("height", svgH);

  const g = svg.append("g");

  // ── Axis baseline ─────────────────────────────────────────────────────────
  g.append("line")
    .attr("x1", LEFT_PAD - 10)
    .attr("x2", LEFT_PAD + axisWidth + 10)
    .attr("y1", baseY)
    .attr("y2", baseY)
    .attr("stroke", "#ccc")
    .attr("stroke-width", AXIS_STROKE);

  // ── Tooltip ───────────────────────────────────────────────────────────────
  const tooltip = d3.select("#tooltip");

  function showTip(event, html_str) {
    tooltip
      .style("opacity", 1)
      .html(html_str)
      .style("left", (event.pageX + 14) + "px")
      .style("top",  (event.pageY - 10) + "px");
  }
  function moveTip(event) {
    tooltip
      .style("left", (event.pageX + 14) + "px")
      .style("top",  (event.pageY - 10) + "px");
  }
  function hideTip() {
    tooltip.style("opacity", 0);
  }

  // ── Highlight state ───────────────────────────────────────────────────────
  // We'll use CSS classes + JS opacity for highlight/dim.
  let activeNode = null;
  let activeLink = null;

  function resetHighlight() {
    activeNode = null;
    activeLink = null;
    arcPaths.attr("opacity", 0.38)
             .attr("stroke-width", function(d) { return swScale(d.w); });
    nodeCircles.attr("opacity", 1);
  }

  function highlightNode(idx) {
    activeNode = idx;
    // Dim all arcs, then brighten incident ones
    arcPaths.attr("opacity", function(d) {
      return (d.i === idx || d.j === idx) ? 0.85 : 0.08;
    });
    nodeCircles.attr("opacity", function(d, i) {
      if (i === idx) return 1;
      // Check if neighbour
      var incident = LINKS.some(function(lk) {
        return (lk.i === idx && lk.j === i) || (lk.j === idx && lk.i === i);
      });
      return incident ? 0.85 : 0.18;
    });
  }

  function highlightLink(lk) {
    activeLink = lk;
    arcPaths.attr("opacity", function(d) {
      return (d === lk) ? 0.92 : 0.07;
    }).attr("stroke-width", function(d) {
      return d === lk ? Math.max(swScale(d.w) + 1.5, 3) : swScale(d.w);
    });
    nodeCircles.attr("opacity", function(d, i) {
      return (i === lk.i || i === lk.j) ? 1 : 0.18;
    });
  }

  // ── Draw arcs (longest first, so short arcs sit on top) ───────────────────
  const arcPaths = g.selectAll("path.arc")
    .data(LINKS)
    .enter()
    .append("path")
    .attr("class", "arc")
    .attr("fill", "none")
    .attr("stroke", ARC_COLOR)
    .attr("stroke-linecap", "round")
    .attr("stroke-width", function(d) { return swScale(d.w); })
    .attr("opacity", 0.38)
    .attr("d", function(d, k) {
      var x1 = xOf(d.i);
      var x2 = xOf(d.j);
      var rawRadius = Math.abs(x2 - x1) / 2;
      var rx = rawRadius;
      var ry = Math.min(rawRadius, capR);  // flatten over-tall arcs
      // sweep 1 = arc above the baseline, 0 = below (two-sided; alternated per link)
      var sweep = sideOf[k] > 0 ? 1 : 0;
      return "M " + x1 + "," + baseY +
             " A " + rx + "," + ry + " 0 0," + sweep + " " + x2 + "," + baseY;
    })
    .on("mouseover", function(event, d) {
      highlightLink(d);
      var wLabel = d.w % 1 === 0 ? d.w : d.w.toFixed(2);
      showTip(event,
        "<strong>" + NAMES[d.i] + "</strong> &harr; <strong>" + NAMES[d.j] + "</strong>" +
        "<br/>Weight: " + wLabel
      );
    })
    .on("mousemove", moveTip)
    .on("mouseout", function() {
      resetHighlight();
      hideTip();
    });

  // ── Draw nodes ────────────────────────────────────────────────────────────
  const nodeData = NAMES.map(function(nm, i) { return { name: nm, deg: DEG[i], rank: i }; });

  const nodeCircles = g.selectAll("circle.node")
    .data(nodeData)
    .enter()
    .append("circle")
    .attr("class", "node")
    .attr("cx", function(d) { return xOf(d.rank); })
    .attr("cy", baseY)
    .attr("r",  function(d) { return rScale(d.deg); })
    .attr("fill",   function(d) { return colScale(d.deg); })
    .attr("stroke", "#fff")
    .attr("stroke-width", 1.2)
    .attr("cursor", "pointer")
    .on("mouseover", function(event, d) {
      highlightNode(d.rank);
      showTip(event,
        "<strong>" + d.name + "</strong>" +
        "<br/>Degree: " + d.deg
      );
    })
    .on("mousemove", moveTip)
    .on("mouseout", function() {
      resetHighlight();
      hideTip();
    });

  // ── Draw labels ───────────────────────────────────────────────────────────
  g.selectAll("text.label")
    .data(nodeData)
    .enter()
    .filter(function(d) { return d.rank % labelStep === 0; })
    .append("text")
    .attr("class", "label")
    .attr("x", function(d) { return xOf(d.rank); })
    .attr("y", labelY)
    .attr("font-size", FONT_SIZE + "px")
    .attr("fill", "#444")
    .attr("text-anchor", "end")
    .attr("transform", function(d) {
      var x = xOf(d.rank);
      return "rotate(-90," + x + "," + labelY + ")";
    })
    .text(function(d) { return d.name; });

  // ── BBox refit ────────────────────────────────────────────────────────────
  // After all marks are drawn, expand the SVG to fit its actual content.
  try {
    var bb = svg.node().getBBox();
    var pad = 10;
    var vx = bb.x - pad;
    var vy = bb.y - pad;
    var vw = bb.width  + pad * 2;
    var vh = bb.height + pad * 2;
    svg.attr("viewBox", vx + " " + vy + " " + vw + " " + vh)
       .attr("width",  vw)
       .attr("height", vh);
  } catch(e) { /* getBBox may fail in some non-browser environments */ }

})();
</script>
</body>
</html>""")

    return "".join(html_parts)


# ---------------------------------------------------------------------------
# No-data fallback
# ---------------------------------------------------------------------------

def _no_data_html(escaped_title):
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"/>"
        "<title>" + escaped_title + "</title></head><body style=\"font-family:sans-serif;"
        "padding:2em;color:#555\">"
        "<h2>" + escaped_title + "</h2>"
        "<p>No data to display.</p></body></html>"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_rows(data_obj, mapping):
    """Accept either a JSON array or the grouped Mondial DB form."""
    if isinstance(data_obj, list):
        return data_obj
    if isinstance(data_obj, dict) and "tables" in data_obj:
        table = mapping.get("table")
        if not table:
            raise ValueError("mapping must include a 'table' field when data is in grouped form")
        tables = data_obj["tables"]
        if table not in tables:
            raise ValueError("Table '{}' not found in data. Available: {}".format(
                table, list(tables.keys())))
        return tables[table]
    raise ValueError("Unrecognised data format: expected a JSON array or {\"tables\": {...}}")


def main():
    parser = argparse.ArgumentParser(description="Arc Diagram renderer (reflexive_many_many)")
    parser.add_argument("--mapping", required=True, help="Path to mapping JSON file")
    parser.add_argument("--data",    required=True, help="Path to data JSON file")
    parser.add_argument("--out",     required=True, help="Path for output HTML file")
    args = parser.parse_args()

    mapping_path = pathlib.Path(args.mapping)
    data_path    = pathlib.Path(args.data)
    out_path     = pathlib.Path(args.out)

    with mapping_path.open("r", encoding="utf-8") as fh:
        mapping = json.load(fh)

    with data_path.open("r", encoding="utf-8") as fh:
        data_obj = json.load(fh)

    # Accept mapping wrapped in a stage-1/2 result object
    if "chart_mapping" in mapping:
        mapping = mapping["chart_mapping"]
    elif "selected_visualisation" in mapping:
        mapping = mapping["selected_visualisation"].get("encoding", mapping)

    rows = _load_rows(data_obj, mapping)

    # Pattern guard
    pattern = mapping.get("pattern", "")
    if pattern and "many_many" in pattern and "reflexive" not in pattern:
        print(
            "ERROR: arc_diagram renderer only supports reflexive_many_many_relationship.\n"
            "The supplied mapping has pattern='{}'. Use a different renderer.".format(pattern),
            file=sys.stderr,
        )
        sys.exit(1)

    html_doc = render(mapping, rows)

    out_path.write_text(html_doc, encoding="utf-8")
    print("Written:", out_path)


if __name__ == "__main__":
    main()

