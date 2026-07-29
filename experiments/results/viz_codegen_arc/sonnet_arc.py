# import argparse
# import json
# import html
# import pathlib
# from collections import defaultdict, deque


# # ---------------------------------------------------------------------------
# # Ordering helpers (Reverse Cuthill-McKee + barycenter refinement)
# # ---------------------------------------------------------------------------

# def _build_adj(n_nodes, edges):
#     """Return adjacency list (unweighted) for n_nodes nodes."""
#     adj = defaultdict(set)
#     for i, j, _ in edges:
#         adj[i].add(j)
#         adj[j].add(i)
#     return adj


# def _rcm_order(n_nodes, adj):
#     """
#     Reverse Cuthill-McKee ordering.
#     BFS from the lowest-degree node, visiting neighbours by increasing degree,
#     then reverse the result to cluster connected nodes.
#     """
#     degree = {i: len(adj[i]) for i in range(n_nodes)}
#     visited = [False] * n_nodes
#     order = []

#     # Find the starting node: lowest degree among unvisited
#     def _start():
#         return min((i for i in range(n_nodes) if not visited[i]),
#                    key=lambda x: degree[x])

#     while len(order) < n_nodes:
#         start = _start()
#         queue = deque([start])
#         visited[start] = True
#         while queue:
#             node = queue.popleft()
#             order.append(node)
#             neighbours = sorted(adj[node], key=lambda x: degree[x])
#             for nb in neighbours:
#                 if not visited[nb]:
#                     visited[nb] = True
#                     queue.append(nb)

#     return list(reversed(order))


# def _total_weighted_length(order, edges):
#     """Sum of |pos[i] - pos[j]| * w for all edges (proxy for crossings)."""
#     pos = [0] * len(order)
#     for rank, node in enumerate(order):
#         pos[node] = rank
#     return sum(abs(pos[i] - pos[j]) * w for i, j, w in edges)


# def _barycenter_refine(order, adj, edges, iterations=10):
#     """
#     Barycenter iteration: repeatedly move each node to the weighted mean
#     position of its neighbours and re-sort.
#     """
#     n = len(order)
#     # Build weight lookup
#     weight_map = defaultdict(float)
#     for i, j, w in edges:
#         weight_map[(i, j)] += w
#         weight_map[(j, i)] += w

#     best_order = list(order)
#     best_cost = _total_weighted_length(best_order, edges)

#     current = list(order)
#     for _ in range(iterations):
#         pos = [0.0] * n
#         for rank, node in enumerate(current):
#             pos[node] = float(rank)

#         scores = []
#         for node in range(n):
#             neighbours = list(adj[node])
#             if not neighbours:
#                 scores.append((pos[node], node))
#             else:
#                 total_w = sum(weight_map[(node, nb)] for nb in neighbours)
#                 if total_w == 0:
#                     scores.append((pos[node], node))
#                 else:
#                     bary = sum(weight_map[(node, nb)] * pos[nb]
#                                for nb in neighbours) / total_w
#                     scores.append((bary, node))

#         scores.sort(key=lambda x: x[0])
#         new_order = [node for _, node in scores]
#         cost = _total_weighted_length(new_order, edges)
#         if cost < best_cost:
#             best_cost = cost
#             best_order = new_order
#         current = new_order

#     return best_order


# def _compute_order(n_nodes, edges):
#     """Return the best node order found by RCM + barycenter refinement."""
#     if n_nodes == 0:
#         return []
#     adj = _build_adj(n_nodes, edges)
#     seed = _rcm_order(n_nodes, adj)
#     refined = _barycenter_refine(seed, adj, edges)
#     seed_cost = _total_weighted_length(seed, edges)
#     refined_cost = _total_weighted_length(refined, edges)
#     return refined if refined_cost <= seed_cost else seed


# # ---------------------------------------------------------------------------
# # Main render function
# # ---------------------------------------------------------------------------

# def render(mapping: dict, rows: list) -> str:
#     # ------------------------------------------------------------------
#     # 0. Validate pattern
#     # ------------------------------------------------------------------
#     pattern = mapping.get("pattern", "")
#     if "many_many" in pattern and "reflexive" not in pattern:
#         raise ValueError(
#             "Arc diagram renderer only supports reflexive_many_many_relationship. "
#             "Received pattern: " + repr(pattern)
#         )

#     # ------------------------------------------------------------------
#     # 1. Read column names from mapping
#     # ------------------------------------------------------------------
#     src_col = mapping["source"]
#     tgt_col = mapping["target"]
#     val_col = mapping.get("value", mapping.get("width", "count"))
#     title_raw = mapping.get("title", "Arc Diagram")
#     title_escaped = html.escape(str(title_raw))

#     # ------------------------------------------------------------------
#     # 2. Build node set and aggregate edges
#     # ------------------------------------------------------------------
#     node_set = set()
#     for row in rows:
#         s = row.get(src_col)
#         t = row.get(tgt_col)
#         if s is not None:
#             node_set.add(str(s))
#         if t is not None:
#             node_set.add(str(t))

#     # Sorted list of all node names (initial sort; will be reordered)
#     all_names = sorted(node_set)
#     name_to_idx = {name: i for i, name in enumerate(all_names)}
#     n_nodes = len(all_names)

#     # Aggregate undirected edges
#     edge_map = defaultdict(float)
#     for row in rows:
#         s = row.get(src_col)
#         t = row.get(tgt_col)
#         if s is None or t is None:
#             continue
#         si = name_to_idx.get(str(s))
#         ti = name_to_idx.get(str(t))
#         if si is None or ti is None:
#             continue
#         if si == ti:
#             continue  # drop self-loops
#         key = (min(si, ti), max(si, ti))
#         if val_col == "count":
#             edge_map[key] += 1.0
#         else:
#             try:
#                 w = float(row.get(val_col, 1))
#             except (TypeError, ValueError):
#                 w = 1.0
#             edge_map[key] += w

#     # Raw edges list: (i, j, w) with i < j
#     raw_edges = [(i, j, w) for (i, j), w in edge_map.items()]

#     # ------------------------------------------------------------------
#     # 3. Degenerate data guard
#     # ------------------------------------------------------------------
#     if n_nodes == 0 or len(raw_edges) == 0:
#         return (
#             "<!DOCTYPE html><html><head><meta charset='utf-8'>"
#             "<title>" + title_escaped + "</title></head>"
#             "<body style='font-family:sans-serif;padding:2em;'>"
#             "<h2>" + title_escaped + "</h2>"
#             "<p>No data to display.</p>"
#             "</body></html>"
#         )

#     # ------------------------------------------------------------------
#     # 4. Compute axis order (minimise arc crossings)
#     # ------------------------------------------------------------------
#     best_order = _compute_order(n_nodes, raw_edges)
#     # best_order[rank] = original index
#     # new_pos[original_index] = rank
#     new_pos = [0] * n_nodes
#     for rank, orig in enumerate(best_order):
#         new_pos[orig] = rank

#     # Reordered names list
#     ordered_names = [all_names[orig] for orig in best_order]

#     # Remap edges to new positions
#     remapped_edges = []
#     for i, j, w in raw_edges:
#         ni, nj = new_pos[i], new_pos[j]
#         remapped_edges.append((min(ni, nj), max(ni, nj), w))

#     # ------------------------------------------------------------------
#     # 5. Compute per-node degree (unweighted)
#     # ------------------------------------------------------------------
#     degree = [0] * n_nodes
#     for ni, nj, _ in remapped_edges:
#         degree[ni] += 1
#         degree[nj] += 1

#     # ------------------------------------------------------------------
#     # 6. Escape names for safe HTML/JS embedding
#     # ------------------------------------------------------------------
#     escaped_names = [html.escape(name) for name in ordered_names]

#     # ------------------------------------------------------------------
#     # 7. Serialise data for injection
#     # ------------------------------------------------------------------
#     def safe_json(obj):
#         return json.dumps(obj).replace("</", "<\\/")

#     names_json = safe_json(escaped_names)
#     deg_json = safe_json(degree)

#     links_list = [{"i": ni, "j": nj, "w": w} for ni, nj, w in remapped_edges]
#     links_json = safe_json(links_list)

#     val_label = "count" if val_col == "count" else html.escape(str(val_col))
#     subtitle_text = html.escape(
#         "Arc thickness \u2192 " + val_label + "   \u2022   Node size & colour \u2192 degree"
#     )

#     # ------------------------------------------------------------------
#     # 8. Build HTML via string concatenation (no f-strings / .format)
#     # ------------------------------------------------------------------

#     # The JavaScript template uses __NAMES__, __DEG__, __LINKS__,
#     # __TITLE__, __SUBTITLE__ as replacement tokens.

#     js_template = """
#     const names = __NAMES__;
#     const deg   = __DEG__;
#     const links = __LINKS__;
#     const TITLE    = __TITLE__;
#     const SUBTITLE = __SUBTITLE__;

#     // ---- layout constants ----
#     const NODE_PAD   = 60;   // left/right padding before first/after last node
#     const TOP_PAD    = 24;   // space above the tallest arc apex
#     const BOTTOM_PAD = 20;   // space below labels
#     const MIN_NODE_R = 2;
#     const MAX_NODE_R = 10;
#     const FONT_SIZE  = 9;
#     const LABEL_ANGLE = -90; // degrees, rotated below axis

#     const n = names.length;

#     // ---- x scale ----
#     const totalWidth = Math.max(900, n * 18 + NODE_PAD * 2);
#     const xScale = d3.scalePoint()
#         .domain(d3.range(n))
#         .range([NODE_PAD, totalWidth - NODE_PAD])
#         .padding(0.5);

#     // ---- compute maxR (tallest arc) ----
#     let maxR = 0;
#     links.forEach(function(lk) {
#         const r = Math.abs(xScale(lk.j) - xScale(lk.i)) / 2;
#         if (r > maxR) maxR = r;
#     });

#     // ---- longest label for labelSpace ----
#     let maxLabelLen = 0;
#     names.forEach(function(nm) { if (nm.length > maxLabelLen) maxLabelLen = nm.length; });
#     const labelSpace = maxLabelLen * FONT_SIZE * 0.62 + 12;

#     const baseY  = maxR + TOP_PAD;
#     const svgH   = baseY + labelSpace + BOTTOM_PAD;
#     const svgW   = totalWidth;

#     // ---- scales ----
#     const maxDeg = d3.max(deg) || 1;
#     const rScale = d3.scaleSqrt().domain([0, maxDeg]).range([MIN_NODE_R, MAX_NODE_R]);
#     const colScale = d3.scaleSequential(d3.interpolateViridis).domain([0, maxDeg]);

#     const wExtent = d3.extent(links, function(lk) { return lk.w; });
#     const strokeScale = d3.scaleSqrt()
#         .domain([wExtent[0], wExtent[1]])
#         .range([1, 6])
#         .clamp(true);

#     // ---- SVG ----
#     const svg = d3.select("#chart")
#         .append("svg")
#         .attr("width",  svgW)
#         .attr("height", svgH)
#         .style("display", "block")
#         .style("margin", "0 auto");

#     // title
#     svg.append("text")
#         .attr("x", svgW / 2).attr("y", 18)
#         .attr("text-anchor", "middle")
#         .attr("font-size", 15).attr("font-weight", "bold")
#         .attr("font-family", "sans-serif").attr("fill", "#222")
#         .text(TITLE);

#     svg.append("text")
#         .attr("x", svgW / 2).attr("y", 34)
#         .attr("text-anchor", "middle")
#         .attr("font-size", 10).attr("fill", "#666")
#         .attr("font-family", "sans-serif")
#         .text(SUBTITLE);

#     const g = svg.append("g").attr("transform", "translate(0,0)");

#     // baseline
#     g.append("line")
#         .attr("x1", NODE_PAD - 10).attr("x2", totalWidth - NODE_PAD + 10)
#         .attr("y1", baseY).attr("y2", baseY)
#         .attr("stroke", "#ccc").attr("stroke-width", 1);

#     // ---- tooltip ----
#     const tooltip = d3.select("body").append("div")
#         .attr("id", "tooltip")
#         .style("position", "absolute")
#         .style("background", "rgba(255,255,255,0.95)")
#         .style("border", "1px solid #bbb")
#         .style("border-radius", "4px")
#         .style("padding", "6px 10px")
#         .style("font-size", "12px")
#         .style("font-family", "sans-serif")
#         .style("pointer-events", "none")
#         .style("display", "none")
#         .style("box-shadow", "0 2px 6px rgba(0,0,0,0.15)");

#     // ---- draw arcs (longest first so short arcs sit on top) ----
#     const sortedLinks = links.slice().sort(function(a, b) {
#         return Math.abs(xScale(b.j) - xScale(b.i)) - Math.abs(xScale(a.j) - xScale(a.i));
#     });

#     const arcPaths = g.selectAll(".arc")
#         .data(sortedLinks)
#         .enter().append("path")
#         .attr("class", "arc")
#         .attr("fill", "none")
#         .attr("stroke", "#4477aa")
#         .attr("stroke-linecap", "round")
#         .attr("stroke-opacity", 0.35)
#         .attr("stroke-width", function(lk) { return strokeScale(lk.w); })
#         .attr("d", function(lk) {
#             const x1 = xScale(lk.i);
#             const x2 = xScale(lk.j);
#             const r  = Math.abs(x2 - x1) / 2;
#             return "M " + x1 + "," + baseY + " A " + r + "," + r + " 0 0,1 " + x2 + "," + baseY;
#         })
#         .on("mouseover", function(event, lk) {
#             d3.select(this).attr("stroke-opacity", 0.95).attr("stroke", "#cc4400");
#             tooltip
#                 .style("display", "block")
#                 .html("<strong>" + names[lk.i] + "</strong> &harr; <strong>" + names[lk.j] + "</strong><br/>weight: " + (+lk.w.toFixed(4)));
#         })
#         .on("mousemove", function(event) {
#             tooltip
#                 .style("left", (event.pageX + 12) + "px")
#                 .style("top",  (event.pageY - 28) + "px");
#         })
#         .on("mouseout", function() {
#             d3.select(this).attr("stroke-opacity", 0.35).attr("stroke", "#4477aa");
#             tooltip.style("display", "none");
#         });

#     // ---- draw nodes ----
#     // Determine label thinning: show every k-th label when nodes are dense
#     const step = Math.ceil(n / 80);

#     const nodeG = g.selectAll(".node")
#         .data(d3.range(n))
#         .enter().append("g")
#         .attr("class", "node")
#         .attr("transform", function(i) { return "translate(" + xScale(i) + "," + baseY + ")"; })
#         .style("cursor", "pointer");

#     nodeG.append("circle")
#         .attr("r", function(i) { return rScale(deg[i]); })
#         .attr("fill", function(i) { return colScale(deg[i]); })
#         .attr("stroke", "#fff")
#         .attr("stroke-width", 1.2);

#     nodeG.filter(function(i) { return i % step === 0; })
#         .append("text")
#         .attr("transform", "rotate(" + LABEL_ANGLE + ")")
#         .attr("dy", "-4")
#         .attr("text-anchor", "start")
#         .attr("font-size", FONT_SIZE + "px")
#         .attr("font-family", "sans-serif")
#         .attr("fill", "#333")
#         .text(function(i) { return names[i]; });

#     // node hover
#     nodeG.on("mouseover", function(event, i) {
#             // highlight incident arcs
#             arcPaths.attr("stroke-opacity", function(lk) {
#                 return (lk.i === i || lk.j === i) ? 0.9 : 0.05;
#             }).attr("stroke", function(lk) {
#                 return (lk.i === i || lk.j === i) ? "#cc4400" : "#4477aa";
#             });
#             // highlight neighbour nodes
#             nodeG.select("circle").attr("opacity", function(j) {
#                 if (j === i) return 1;
#                 const linked = links.some(function(lk) {
#                     return (lk.i === i && lk.j === j) || (lk.j === i && lk.i === j);
#                 });
#                 return linked ? 1 : 0.15;
#             });
#             tooltip
#                 .style("display", "block")
#                 .html("<strong>" + names[i] + "</strong><br/>degree: " + deg[i]);
#         })
#         .on("mousemove", function(event) {
#             tooltip
#                 .style("left", (event.pageX + 12) + "px")
#                 .style("top",  (event.pageY - 28) + "px");
#         })
#         .on("mouseout", function() {
#             arcPaths.attr("stroke-opacity", 0.35).attr("stroke", "#4477aa");
#             nodeG.select("circle").attr("opacity", 1);
#             tooltip.style("display", "none");
#         });

#     // ---- refit SVG to content ----
#     (function() {
#         try {
#             const bb = svg.node().getBBox();
#             const pad = 16;
#             svg.attr("viewBox", (bb.x - pad) + " " + (bb.y - pad) + " " +
#                                  (bb.width + pad * 2) + " " + (bb.height + pad * 2))
#                .attr("width",  bb.width  + pad * 2)
#                .attr("height", bb.height + pad * 2);
#         } catch(e) { /* getBBox may fail in some environments; ignore */ }
#     })();
# """

#     js_filled = (js_template
#                  .replace("__NAMES__",    names_json)
#                  .replace("__DEG__",      deg_json)
#                  .replace("__LINKS__",    links_json)
#                  .replace("__TITLE__",    safe_json(title_escaped))
#                  .replace("__SUBTITLE__", safe_json(subtitle_text)))

#     html_parts = [
#         "<!DOCTYPE html>",
#         "<html lang=\"en\">",
#         "<head>",
#         "  <meta charset=\"utf-8\">",
#         "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
#         "  <title>" + title_escaped + "</title>",
#         "  <style>",
#         "    body { margin: 0; background: #fafafa; font-family: sans-serif; }",
#         "    #chart { width: 100%; overflow-x: auto; padding: 16px 0; box-sizing: border-box; text-align: center; }",
#         "    svg { display: block; margin: 0 auto; }",
#         "  </style>",
#         "</head>",
#         "<body>",
#         "  <div id=\"chart\"></div>",
#         "  <script src=\"https://d3js.org/d3.v7.min.js\"></script>",
#         "  <script>",
#         js_filled,
#         "  </script>",
#         "</body>",
#         "</html>",
#     ]

#     return "\n".join(html_parts)


# # ---------------------------------------------------------------------------
# # CLI
# # ---------------------------------------------------------------------------

# def main():
#     parser = argparse.ArgumentParser(description="Render an arc diagram for a reflexive many-many relationship.")
#     parser.add_argument("--mapping", required=True, help="Path to mapping JSON file")
#     parser.add_argument("--data",    required=True, help="Path to data JSON file (array or Mondial grouped DB)")
#     parser.add_argument("--out",     required=True, help="Output HTML file path")
#     args = parser.parse_args()

#     mapping_path = pathlib.Path(args.mapping)
#     data_path    = pathlib.Path(args.data)
#     out_path     = pathlib.Path(args.out)

#     with mapping_path.open(encoding="utf-8") as f:
#         mapping = json.load(f)

#     # Support bare mapping or Stage-1/2 result object
#     if "chart_mapping" in mapping:
#         mapping = mapping["chart_mapping"]
#     elif "selected_visualisation" in mapping:
#         mapping = mapping["selected_visualisation"]["encoding"]

#     with data_path.open(encoding="utf-8") as f:
#         raw = json.load(f)

#     # Support grouped Mondial DB or plain array
#     if isinstance(raw, dict) and "tables" in raw:
#         table = mapping.get("table")
#         if not table:
#             raise ValueError("Mapping must include a 'table' field when data is the grouped Mondial DB.")
#         rows = raw["tables"][table]
#     elif isinstance(raw, list):
#         rows = raw
#     else:
#         raise ValueError("Data file must be a JSON array or a Mondial grouped DB object.")

#     html_out = render(mapping, rows)

#     out_path.parent.mkdir(parents=True, exist_ok=True)
#     with out_path.open("w", encoding="utf-8") as f:
#         f.write(html_out)

#     print("Written:", out_path)


# if __name__ == "__main__":
#     main()

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

  // ── SVG dimensions ────────────────────────────────────────────────────────
  const baseY    = maxR + TOP_PAD;
  const svgW     = axisWidth + LEFT_PAD + RIGHT_PAD;
  const svgH     = baseY + labelSpace + BOTTOM_PAD;

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
    .attr("d", function(d) {
      var x1 = xOf(d.i);
      var x2 = xOf(d.j);
      var rawRadius = Math.abs(x2 - x1) / 2;
      var rx = rawRadius;
      var ry = Math.min(rawRadius, capR);  // flatten over-tall arcs
      // SVG elliptical arc: M x1,baseY A rx,ry 0 0,1 x2,baseY
      return "M " + x1 + "," + baseY +
             " A " + rx + "," + ry + " 0 0,1 " + x2 + "," + baseY;
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
    .attr("y", baseY + 4)
    .attr("font-size", FONT_SIZE + "px")
    .attr("fill", "#444")
    .attr("text-anchor", "end")
    .attr("transform", function(d) {
      var x = xOf(d.rank);
      return "rotate(-90," + x + "," + (baseY + 4) + ")";
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

