import argparse
import json
import html
import pathlib
import math


# ---------------------------------------------------------------------------
# Spectral / Fiedler ordering helpers (pure Python, deterministic)
# ---------------------------------------------------------------------------

def _mat_vec(adj, v):
    """Sparse adjacency matrix times vector (adj is dict-of-dict {i:{j:w}})."""
    n = len(v)
    result = [0.0] * n
    for i, nbrs in adj.items():
        for j, w in nbrs.items():
            result[i] += w * v[j]
    return result


def _laplacian_vec(adj, degrees, v):
    """Laplacian L = D - A applied to v."""
    n = len(v)
    av = _mat_vec(adj, v)
    return [degrees[i] * v[i] - av[i] for i in range(n)]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _norm(v):
    return math.sqrt(_dot(v, v))


def _normalize(v):
    n = _norm(v)
    if n < 1e-12:
        return v[:]
    return [x / n for x in v]


def _power_iteration_fiedler(n, adj, degrees, max_iter=200):
    """
    Approximate the Fiedler vector (second-smallest Laplacian eigenvector)
    via shifted inverse-free power iteration on (lambda_max*I - L).
    We use a fixed seed for determinism.
    """
    if n == 1:
        return [0.0]

    # Fixed seed vector
    v = [math.sin(i + 1) for i in range(n)]
    v = _normalize(v)

    # Estimate lambda_max via a few power steps on L
    lmax = 1.0
    tmp = v[:]
    for _ in range(30):
        tmp = _laplacian_vec(adj, degrees, tmp)
        lmax = _norm(tmp)
        if lmax < 1e-12:
            break
        tmp = _normalize(tmp)

    # Shift: work with (lmax*I - L) to turn smallest -> largest
    # We want the vector orthogonal to the all-ones vector
    ones = _normalize([1.0] * n)

    def shifted_lap(vec):
        lv = _laplacian_vec(adj, degrees, vec)
        return [lmax * vec[i] - lv[i] for i in range(n)]

    v = [math.sin(i * 1.7 + 0.3) for i in range(n)]
    # Orthogonalize against ones
    dot_ones = _dot(v, ones)
    v = [v[i] - dot_ones * ones[i] for i in range(n)]
    v = _normalize(v)

    for _ in range(max_iter):
        v2 = shifted_lap(v)
        # Orthogonalize against ones
        dot_ones = _dot(v2, ones)
        v2 = [v2[i] - dot_ones * ones[i] for i in range(n)]
        nrm = _norm(v2)
        if nrm < 1e-12:
            break
        v = [x / nrm for x in v2]

    return v


def _connected_components(n, adj):
    """Return list of lists of node indices, one per connected component."""
    visited = [False] * n
    components = []
    for start in range(n):
        if visited[start]:
            continue
        comp = []
        stack = [start]
        while stack:
            node = stack.pop()
            if visited[node]:
                continue
            visited[node] = True
            comp.append(node)
            for nbr in adj.get(node, {}):
                if not visited[nbr]:
                    stack.append(nbr)
        components.append(comp)
    return components


def _circular_span(order, weight_matrix):
    """Total weighted circular span sum_w * min(d, N-d)."""
    n = len(order)
    if n == 0:
        return 0.0
    rank = [0] * n
    for r, idx in enumerate(order):
        rank[idx] = r
    total = 0.0
    for i in range(n):
        for j, w in weight_matrix.get(i, {}).items():
            if j > i:
                d = abs(rank[i] - rank[j])
                total += w * min(d, n - d)
    return total


def _circular_barycenter_refine(order, weight_matrix, iterations=10):
    """Refine a circular ordering by pulling each node to the angular mean of neighbours."""
    n = len(order)
    if n <= 2:
        return order[:]

    best_order = order[:]
    best_cost = _circular_span(order, weight_matrix)

    current = order[:]
    for _ in range(iterations):
        rank = [0] * n
        for r, idx in enumerate(current):
            rank[idx] = r

        angles = [0.0] * n
        for node in range(n):
            nbrs = weight_matrix.get(node, {})
            if not nbrs:
                angles[node] = 2 * math.pi * rank[node] / n
                continue
            sx, sy = 0.0, 0.0
            for nbr, w in nbrs.items():
                theta = 2 * math.pi * rank[nbr] / n
                sx += w * math.cos(theta)
                sy += w * math.sin(theta)
            angles[node] = math.atan2(sy, sx)

        new_order = sorted(range(n), key=lambda nd: angles[nd])
        cost = _circular_span(new_order, weight_matrix)
        if cost < best_cost:
            best_cost = cost
            best_order = new_order[:]
        current = new_order

    return best_order


def spectral_circular_order(n, weight_matrix):
    """
    Order n nodes to minimise circular chord crossings.
    1. Build Laplacian, find Fiedler vector per component.
    2. Refine with circular barycenter.
    Returns a list of node indices in the desired ring order.
    """
    if n == 0:
        return []
    if n == 1:
        return [0]

    # Build adjacency and degrees
    adj = {}
    degrees = [0.0] * n
    for i, nbrs in weight_matrix.items():
        for j, w in nbrs.items():
            adj.setdefault(i, {})[j] = w
            adj.setdefault(j, {})[i] = w
            degrees[i] += w
            degrees[j] += w

    components = _connected_components(n, adj)

    # Order each component by Fiedler vector
    global_order = []
    for comp in components:
        if len(comp) == 1:
            global_order.extend(comp)
            continue
        # Build local sub-problem
        local_idx = {g: l for l, g in enumerate(comp)}
        m = len(comp)
        local_adj = {}
        local_deg = [0.0] * m
        for g in comp:
            l = local_idx[g]
            for gn, w in adj.get(g, {}).items():
                if gn in local_idx:
                    ln = local_idx[gn]
                    local_adj.setdefault(l, {})[ln] = w
                    local_deg[l] += w

        fiedler = _power_iteration_fiedler(m, local_adj, local_deg)
        local_order = sorted(range(m), key=lambda i: fiedler[i])
        global_order.extend(comp[local_order[i]] for i in range(m))

    # Refine with circular barycenter
    refined = _circular_barycenter_refine(global_order, weight_matrix)
    return refined


# ---------------------------------------------------------------------------
# Core render function
# ---------------------------------------------------------------------------

def render(mapping: dict, rows: list) -> str:
    src_col = mapping["source"]
    tgt_col = mapping["target"]
    wid_col = mapping["width"]
    title = mapping.get("title", "Chord Diagram")
    pattern = mapping.get("pattern", "")

    # Collect all source and target values
    all_sources = set()
    all_targets = set()
    for row in rows:
        s = row.get(src_col)
        t = row.get(tgt_col)
        if s is not None:
            all_sources.add(str(s))
        if t is not None:
            all_targets.add(str(t))

    # Determine pattern
    if not pattern:
        if all_sources.isdisjoint(all_targets):
            pattern = "many_many_relationship"
        else:
            pattern = "reflexive_many_many_relationship"

    is_reflexive = (pattern == "reflexive_many_many_relationship")

    # Build node list
    if is_reflexive:
        all_nodes_set = all_sources | all_targets
        all_nodes_list = sorted(all_nodes_set)
        n = len(all_nodes_list)
        node_index = {name: i for i, name in enumerate(all_nodes_list)}
        # group: all 0 for reflexive
        node_group = [0] * n
    else:
        # many_many: sources first, then targets (disjoint)
        src_list = sorted(all_sources)
        tgt_only = sorted(all_targets - all_sources)
        all_nodes_list = src_list + tgt_only
        n = len(all_nodes_list)
        node_index = {name: i for i, name in enumerate(all_nodes_list)}
        node_group = [0] * len(src_list) + [1] * len(tgt_only)

    # Handle empty data
    if n == 0:
        escaped_title = html.escape(title)
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>" + escaped_title + "</title></head>"
            "<body style='font-family:sans-serif;text-align:center;padding:2em;'>"
            "<h2>" + escaped_title + "</h2>"
            "<p>No data to display.</p>"
            "</body></html>"
        )

    # Build weight matrix (sparse dict-of-dict for ordering, then dense for D3)
    weight_matrix = {}  # {i: {j: w}}
    for row in rows:
        s = row.get(src_col)
        t = row.get(tgt_col)
        w_raw = row.get(wid_col, 0)
        if s is None or t is None:
            continue
        try:
            w = float(w_raw) if w_raw is not None else 0.0
        except (ValueError, TypeError):
            w = 0.0
        i = node_index.get(str(s))
        j = node_index.get(str(t))
        if i is None or j is None:
            continue
        weight_matrix.setdefault(i, {})[j] = weight_matrix.get(i, {}).get(j, 0.0) + w
        weight_matrix.setdefault(j, {})[i] = weight_matrix.get(j, {}).get(i, 0.0) + w

    # Apply spectral ordering for reflexive; keep group order for many_many
    if is_reflexive and n > 2:
        order = spectral_circular_order(n, weight_matrix)
        # Reorder names and remap indices
        all_nodes_list = [all_nodes_list[i] for i in order]
        old_to_new = {old: new for new, old in enumerate(order)}
        node_index = {name: old_to_new[old_idx]
                      for name, old_idx in node_index.items()}
        node_group = [node_group[i] for i in order]
        # Rebuild weight matrix with new indices
        new_wm = {}
        for i, nbrs in weight_matrix.items():
            ni = old_to_new[i]
            for j, w in nbrs.items():
                nj = old_to_new[j]
                new_wm.setdefault(ni, {})[nj] = new_wm.get(ni, {}).get(nj, 0.0) + w
        weight_matrix = new_wm

    # Build dense N×N matrix
    matrix = [[0.0] * n for _ in range(n)]
    for i, nbrs in weight_matrix.items():
        for j, w in nbrs.items():
            matrix[i][j] = w

    # Escape names for safe HTML/JS embedding
    escaped_names = [html.escape(name) for name in all_nodes_list]

    # Serialize to JSON (script-safe)
    def safe_json(obj):
        return json.dumps(obj).replace("</", "<\\/")

    names_json = safe_json(escaped_names)
    matrix_json = safe_json(matrix)
    node_group_json = safe_json(node_group)
    title_json = safe_json(html.escape(title))

    # Source/target label for legend (many_many)
    src_label = html.escape(src_col)
    tgt_label = html.escape(tgt_col)
    src_label_json = safe_json(src_label)
    tgt_label_json = safe_json(tgt_label)
    is_reflexive_json = safe_json(is_reflexive)
    width_col_json = safe_json(html.escape(wid_col))

    # Build HTML using string concatenation (no f-strings, no .format)
    html_parts = []

    html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>""")
    html_parts.append(html.escape(title))
    html_parts.append("""</title>
<style>
  body {
    margin: 0;
    background: #f8f9fa;
    font-family: 'Segoe UI', Arial, sans-serif;
  }
  #chart-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 20px;
  }
  h1 {
    font-size: 1.4em;
    color: #333;
    margin-bottom: 8px;
    text-align: center;
  }
  svg {
    display: block;
    margin: 0 auto;
  }
  .tooltip {
    position: absolute;
    background: rgba(0,0,0,0.82);
    color: #fff;
    padding: 8px 13px;
    border-radius: 6px;
    font-size: 13px;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s;
    max-width: 280px;
    word-break: break-word;
    z-index: 100;
  }
  .legend {
    display: flex;
    gap: 18px;
    margin-top: 10px;
    font-size: 13px;
    color: #444;
    flex-wrap: wrap;
    justify-content: center;
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .legend-swatch {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    display: inline-block;
  }
  #no-data {
    font-size: 1.1em;
    color: #888;
    margin-top: 60px;
  }
</style>
</head>
<body>
<div id="chart-container">
  <h1 id="chart-title"></h1>
  <div id="legend" class="legend"></div>
  <div id="chart"></div>
  <div id="no-data" style="display:none">No data to display.</div>
</div>
<div class="tooltip" id="tooltip"></div>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
(function() {
  const TITLE = """ + title_json + """;
  const names = """ + names_json + """;
  const matrix = """ + matrix_json + """;
  const nodeGroup = """ + node_group_json + """;
  const isReflexive = """ + is_reflexive_json + """;
  const srcLabel = """ + src_label_json + """;
  const tgtLabel = """ + tgt_label_json + """;
  const widthCol = """ + width_col_json + """;

  document.getElementById('chart-title').textContent = TITLE;

  const N = names.length;

  // Check for empty data
  const totalWeight = matrix.reduce((s, row) => s + row.reduce((a, b) => a + b, 0), 0);
  if (N === 0 || totalWeight === 0) {
    document.getElementById('no-data').style.display = '';
    return;
  }

  // Dimensions
  const outerRadius = Math.min(420, Math.max(220, 30 + N * 9));
  const innerRadius = outerRadius - 22;
  const labelRadius = outerRadius + 10;
  const svgSize = (outerRadius + 100) * 2;
  const width = svgSize;
  const height = svgSize;

  // Colour scales
  let colourFn;
  if (isReflexive) {
    const scale = d3.scaleSequential(d3.interpolateRainbow).domain([0, N]);
    colourFn = (i) => scale(i);
  } else {
    const srcCount = nodeGroup.filter(g => g === 0).length;
    const tgtCount = nodeGroup.filter(g => g === 1).length;
    const blueScale = d3.scaleSequential(d3.interpolateBlues).domain([-0.5, srcCount + 0.5]);
    const orangeScale = d3.scaleSequential(d3.interpolateOranges).domain([-0.5, tgtCount + 0.5]);
    let srcIdx = 0, tgtIdx = 0;
    const nodeColours = names.map((_, i) => {
      if (nodeGroup[i] === 0) return blueScale(srcIdx++);
      else return orangeScale(tgtIdx++);
    });
    colourFn = (i) => nodeColours[i];
  }

  // Chord layout
  const chord = d3.chord()
    .padAngle(Math.max(0.01, Math.min(0.04, 0.5 / N)))
    .sortSubgroups(d3.descending);

  const chords = chord(matrix);

  // Arc generator
  const arc = d3.arc()
    .innerRadius(innerRadius)
    .outerRadius(outerRadius);

  // Ribbon generator
  const ribbon = d3.ribbon().radius(innerRadius);

  // SVG
  const svg = d3.select('#chart')
    .append('svg')
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', '0 0 ' + width + ' ' + height)
    .style('max-width', '100%');

  const g = svg.append('g')
    .attr('transform', 'translate(' + (width / 2) + ',' + (height / 2) + ')');

  // Tooltip
  const tooltip = d3.select('#tooltip');

  function showTooltip(event, html_content) {
    tooltip
      .style('opacity', 1)
      .html(html_content)
      .style('left', (event.pageX + 14) + 'px')
      .style('top', (event.pageY - 28) + 'px');
  }
  function moveTooltip(event) {
    tooltip
      .style('left', (event.pageX + 14) + 'px')
      .style('top', (event.pageY - 28) + 'px');
  }
  function hideTooltip() {
    tooltip.style('opacity', 0);
  }

  // Draw ribbons
  const ribbonPaths = g.append('g')
    .attr('fill-opacity', 0.72)
    .selectAll('path')
    .data(chords)
    .join('path')
    .attr('d', ribbon)
    .attr('fill', d => colourFn(d.source.index))
    .attr('stroke', d => d3.rgb(colourFn(d.source.index)).darker())
    .attr('stroke-width', 0.5)
    .on('mouseover', function(event, d) {
      const si = d.source.index;
      const ti = d.target.index;
      const val = (matrix[si][ti] + (si !== ti ? matrix[ti][si] : 0)).toFixed(2);
      const content = '<strong>' + names[si] + '</strong> &harr; <strong>' + names[ti] + '</strong>'
        + '<br>' + widthCol + ': <strong>' + val + '</strong>';
      showTooltip(event, content);
      // Emphasise
      ribbonPaths.attr('fill-opacity', rd =>
        (rd.source.index === si && rd.target.index === ti) ||
        (rd.source.index === ti && rd.target.index === si) ? 0.92 : 0.08);
      groupArcs.attr('opacity', gd =>
        gd.index === si || gd.index === ti ? 1.0 : 0.3);
    })
    .on('mousemove', moveTooltip)
    .on('mouseout', function() {
      hideTooltip();
      ribbonPaths.attr('fill-opacity', 0.72);
      groupArcs.attr('opacity', 1.0);
    });

  // Draw group arcs
  const groupArcs = g.append('g')
    .selectAll('g')
    .data(chords.groups)
    .join('g');

  groupArcs.append('path')
    .attr('d', arc)
    .attr('fill', d => colourFn(d.index))
    .attr('stroke', d => d3.rgb(colourFn(d.index)).darker())
    .attr('stroke-width', 0.8)
    .on('mouseover', function(event, d) {
      const i = d.index;
      const rowSum = matrix[i].reduce((a, b) => a + b, 0);
      const content = '<strong>' + names[i] + '</strong>'
        + '<br>Total ' + widthCol + ': <strong>' + rowSum.toFixed(2) + '</strong>';
      showTooltip(event, content);
      ribbonPaths.attr('fill-opacity', rd =>
        rd.source.index === i || rd.target.index === i ? 0.92 : 0.08);
      groupArcs.attr('opacity', gd => gd.index === i ? 1.0 : 0.3);
    })
    .on('mousemove', moveTooltip)
    .on('mouseout', function() {
      hideTooltip();
      ribbonPaths.attr('fill-opacity', 0.72);
      groupArcs.attr('opacity', 1.0);
    });

  // Labels
  const fontSize = Math.max(8, Math.min(13, Math.floor(900 / N)));

  groupArcs.append('text')
    .each(function(d) { d.angle = (d.startAngle + d.endAngle) / 2; })
    .attr('dy', '0.35em')
    .attr('transform', function(d) {
      const rotate = d.angle * 180 / Math.PI - 90;
      const flip = d.angle > Math.PI ? 'rotate(180)' : '';
      return 'rotate(' + rotate + ') translate(' + labelRadius + ',0) ' + flip;
    })
    .attr('text-anchor', d => d.angle > Math.PI ? 'end' : 'start')
    .attr('font-size', fontSize + 'px')
    .attr('fill', '#333')
    .attr('font-family', 'Segoe UI, Arial, sans-serif')
    .text(d => {
      const name = names[d.index];
      const maxLen = Math.max(6, Math.floor(1800 / N));
      return name.length > maxLen ? name.slice(0, maxLen - 1) + '\u2026' : name;
    });

  // Legend for many_many
  if (!isReflexive) {
    const legendEl = document.getElementById('legend');
    const srcCount = nodeGroup.filter(g => g === 0).length;
    const tgtCount = nodeGroup.filter(g => g === 1).length;

    // Pick representative colours
    const srcRepColor = colourFn(0);
    const tgtRepColor = colourFn(srcCount);

    const items = [
      { label: srcLabel + ' (' + srcCount + ')', color: srcRepColor },
      { label: tgtLabel + ' (' + tgtCount + ')', color: tgtRepColor }
    ];
    items.forEach(function(item) {
      const div = document.createElement('div');
      div.className = 'legend-item';
      const swatch = document.createElement('span');
      swatch.className = 'legend-swatch';
      swatch.style.background = item.color;
      const label = document.createElement('span');
      label.textContent = item.label;
      div.appendChild(swatch);
      div.appendChild(label);
      legendEl.appendChild(div);
    });
  }

})();
</script>
</body>
</html>""")

    return "".join(html_parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Chord Diagram Renderer")
    parser.add_argument("--mapping", required=True, help="Path to mapping JSON file")
    parser.add_argument("--data", required=True, help="Path to data JSON file")
    parser.add_argument("--out", required=True, help="Path to output HTML file")
    args = parser.parse_args()

    mapping_path = pathlib.Path(args.mapping)
    data_path = pathlib.Path(args.data)
    out_path = pathlib.Path(args.out)

    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    with open(data_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # Support both plain array and grouped Mondial DB format
    if isinstance(raw_data, dict) and "tables" in raw_data:
        table_name = mapping.get("table", "")
        rows = raw_data["tables"].get(table_name, [])
    elif isinstance(raw_data, list):
        rows = raw_data
    else:
        rows = []

    html_output = render(mapping, rows)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_output)

    print("Written: " + str(out_path))


if __name__ == "__main__":
    main()

# import argparse
# import json
# import math
# import html
# import pathlib


# # ---------------------------------------------------------------------------
# # Spectral / Fiedler ordering helpers (Python, run at render time)
# # ---------------------------------------------------------------------------

# def _build_adjacency(names, matrix):
#     n = len(names)
#     adj = [[0.0] * n for _ in range(n)]
#     for i in range(n):
#         for j in range(n):
#             if matrix[i][j]:
#                 adj[i][j] = float(matrix[i][j])
#     return adj


# def _laplacian(adj, n):
#     L = [[0.0] * n for _ in range(n)]
#     for i in range(n):
#         deg = sum(adj[i])
#         L[i][i] = deg
#         for j in range(n):
#             L[i][j] -= adj[i][j]
#     return L


# def _power_fiedler(L, n, seed_vec, iterations=200):
#     """Approximate Fiedler vector via shifted inverse-power iteration (no numpy)."""
#     # We want the eigenvector for the 2nd-smallest eigenvalue.
#     # Strategy: deflate the trivial zero eigenvector (all-ones) and use
#     # power iteration on the Laplacian (smallest non-zero eigenvalue).
#     # For small n this converges adequately.
#     EPS = 1e-12

#     def dot(a, b):
#         return sum(a[i] * b[i] for i in range(n))

#     def norm(a):
#         return math.sqrt(dot(a, a))

#     def matvec(M, v):
#         return [sum(M[i][j] * v[j] for j in range(n)) for i in range(n)]

#     def sub(a, b):
#         return [a[i] - b[i] for i in range(n)]

#     def scale(a, s):
#         return [a[i] * s for i in range(n)]

#     def project_out_ones(v):
#         # Remove component along the all-ones vector
#         mean = sum(v) / n
#         return [x - mean for x in v]

#     # Shift: L_shift = L + shift*I  so smallest eigenvalue becomes positive
#     # Use shift = max diagonal + 1 to make it positive definite after deflation
#     shift = max(L[i][i] for i in range(n)) + 1.0

#     # Build shifted matrix
#     Ls = [row[:] for row in L]
#     for i in range(n):
#         Ls[i][i] += shift

#     # Start from seed
#     v = seed_vec[:]
#     v = project_out_ones(v)
#     nv = norm(v)
#     if nv < EPS:
#         v = [float(i) for i in range(n)]
#         v = project_out_ones(v)
#         nv = norm(v)
#     v = scale(v, 1.0 / nv)

#     for _ in range(iterations):
#         # Multiply by Ls
#         w = matvec(Ls, v)
#         # Project out ones
#         w = project_out_ones(w)
#         nw = norm(w)
#         if nw < EPS:
#             break
#         v = scale(w, 1.0 / nw)

#     # The Fiedler vector for the original L is approximately v
#     # (we iterated on Ls which has the same eigenvectors as L)
#     return v


# def _connected_components(adj, n):
#     visited = [False] * n
#     components = []
#     for start in range(n):
#         if not visited[start]:
#             comp = []
#             stack = [start]
#             while stack:
#                 node = stack.pop()
#                 if visited[node]:
#                     continue
#                 visited[node] = True
#                 comp.append(node)
#                 for j in range(n):
#                     if adj[node][j] > 0 and not visited[j]:
#                         stack.append(j)
#             components.append(comp)
#     return components


# def _circular_crossings(order, matrix, n):
#     """Total weighted circular span: sum over edges of w * min(d, n-d)."""
#     pos = [0] * n
#     for rank, idx in enumerate(order):
#         pos[idx] = rank
#     total = 0.0
#     for i in range(n):
#         for j in range(i + 1, n):
#             w = matrix[i][j] + matrix[j][i]
#             if w > 0:
#                 d = abs(pos[i] - pos[j])
#                 total += w * min(d, n - d)
#     return total


# def _circular_barycenter_refine(order, matrix, n, iterations=30):
#     """Refine circular order by pulling each node to angular mean of neighbours."""
#     best_order = order[:]
#     best_cost = _circular_crossings(best_order, matrix, n)

#     current = order[:]
#     for _ in range(iterations):
#         pos = [0.0] * n
#         for rank, idx in enumerate(current):
#             pos[idx] = float(rank)

#         angles = []
#         for idx in range(n):
#             # Angular mean of neighbours
#             sx, sy = 0.0, 0.0
#             total_w = 0.0
#             for j in range(n):
#                 w = matrix[idx][j] + matrix[j][i] if False else (matrix[idx][j] + matrix[j][idx])
#                 if w > 0:
#                     theta = 2.0 * math.pi * pos[j] / n
#                     sx += w * math.cos(theta)
#                     sy += w * math.sin(theta)
#                     total_w += w
#             if total_w > 0:
#                 angle = math.atan2(sy, sx)
#             else:
#                 angle = 2.0 * math.pi * pos[idx] / n
#             angles.append((angle, idx))

#         angles.sort(key=lambda x: x[0])
#         new_order = [idx for _, idx in angles]

#         cost = _circular_crossings(new_order, matrix, n)
#         if cost < best_cost:
#             best_cost = cost
#             best_order = new_order[:]
#         current = new_order[:]

#     return best_order


# def _spectral_order(names, matrix):
#     """Return a permutation of range(len(names)) that minimises chord crossings."""
#     n = len(names)
#     if n <= 2:
#         return list(range(n))

#     adj = _build_adjacency(names, matrix)
#     components = _connected_components(adj, n)

#     # Fixed seed vector (deterministic)
#     seed_full = [math.sin(float(i) + 1.0) for i in range(n)]

#     order = []
#     for comp in components:
#         m = len(comp)
#         if m == 1:
#             order.extend(comp)
#             continue
#         if m == 2:
#             order.extend(comp)
#             continue

#         # Sub-Laplacian
#         sub_adj = [[adj[comp[a]][comp[b]] for b in range(m)] for a in range(m)]
#         L = _laplacian(sub_adj, m)
#         seed = [seed_full[comp[i]] for i in range(m)]
#         fiedler = _power_fiedler(L, m, seed)

#         # Sort component by Fiedler value
#         indexed = sorted(range(m), key=lambda i: fiedler[i])
#         comp_order = [comp[i] for i in indexed]
#         order.extend(comp_order)

#     # Circular barycenter refinement
#     refined = _circular_barycenter_refine(order, matrix, n)
#     return refined


# # ---------------------------------------------------------------------------
# # Matrix builder
# # ---------------------------------------------------------------------------

# def build_matrix(rows, source_col, target_col, width_col, pattern):
#     """
#     Returns (names, matrix, groups) where:
#       names  — ordered list of node labels
#       matrix — N×N list-of-lists (floats)
#       groups — list of 0/1 per name (0=source set, 1=target set); all 0 for reflexive
#     """
#     sources = []
#     targets = []
#     for row in rows:
#         s = row.get(source_col)
#         t = row.get(target_col)
#         if s is not None:
#             sources.append(str(s))
#         if t is not None:
#             targets.append(str(t))

#     source_set = set(sources)
#     target_set = set(targets)

#     # Infer pattern if not given
#     if pattern is None:
#         if source_set.isdisjoint(target_set):
#             pattern = "many_many_relationship"
#         else:
#             pattern = "reflexive_many_many_relationship"

#     is_reflexive = (pattern == "reflexive_many_many_relationship")

#     if is_reflexive:
#         all_nodes = sorted(source_set | target_set)
#         groups_map = {n: 0 for n in all_nodes}
#     else:
#         # bipartite: sources first, then targets (excluding any overlap with sources)
#         src_nodes = sorted(source_set)
#         tgt_nodes = sorted(target_set - source_set)
#         all_nodes = src_nodes + tgt_nodes
#         groups_map = {}
#         for n in src_nodes:
#             groups_map[n] = 0
#         for n in tgt_nodes:
#             groups_map[n] = 1

#     n = len(all_nodes)
#     if n == 0:
#         return [], [], []

#     idx = {name: i for i, name in enumerate(all_nodes)}

#     matrix = [[0.0] * n for _ in range(n)]

#     for row in rows:
#         s = row.get(source_col)
#         t = row.get(target_col)
#         w = row.get(width_col)
#         if s is None or t is None or w is None:
#             continue
#         s, t = str(s), str(t)
#         if s not in idx or t not in idx:
#             continue
#         try:
#             w = float(w)
#         except (TypeError, ValueError):
#             continue
#         i, j = idx[s], idx[t]
#         matrix[i][j] += w
#         if i != j:
#             matrix[j][i] += w

#     # Apply spectral ordering for reflexive only
#     if is_reflexive and n > 2:
#         perm = _spectral_order(all_nodes, matrix)
#         new_names = [all_nodes[p] for p in perm]
#         new_matrix = [[matrix[perm[r]][perm[c]] for c in range(n)] for r in range(n)]
#         new_groups = [groups_map[name] for name in new_names]
#         return new_names, new_matrix, new_groups
#     else:
#         groups = [groups_map[name] for name in all_nodes]
#         return all_nodes, matrix, groups


# # ---------------------------------------------------------------------------
# # HTML / JS template
# # ---------------------------------------------------------------------------

# TEMPLATE = '''<!DOCTYPE html>
# <html lang="en">
# <head>
# <meta charset="UTF-8"/>
# <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
# <title>__TITLE__</title>
# <script src="https://d3js.org/d3.v7.min.js"></script>
# <style>
#   * { box-sizing: border-box; margin: 0; padding: 0; }
#   body {
#     background: #0f1117;
#     color: #e8eaf0;
#     font-family: "Segoe UI", system-ui, sans-serif;
#     min-height: 100vh;
#     display: flex;
#     flex-direction: column;
#     align-items: center;
#     padding: 24px 16px 40px;
#   }
#   h1 {
#     font-size: 1.45rem;
#     font-weight: 600;
#     letter-spacing: .03em;
#     margin-bottom: 6px;
#     text-align: center;
#     color: #c9d1e8;
#   }
#   #subtitle {
#     font-size: .82rem;
#     color: #6b7494;
#     margin-bottom: 18px;
#     text-align: center;
#   }
#   #chart-wrap {
#     display: flex;
#     justify-content: center;
#     width: 100%;
#   }
#   svg { display: block; margin: 0 auto; }
#   .group-arc { cursor: pointer; }
#   .ribbon { fill-opacity: .65; cursor: pointer; transition: fill-opacity .15s; }
#   .ribbon.faded { fill-opacity: .07; }
#   .ribbon.highlighted { fill-opacity: .88; }
#   .group-arc.faded { opacity: .25; }
#   .chord-label {
#     font-size: 11px;
#     fill: #c9d1e8;
#     pointer-events: none;
#     dominant-baseline: middle;
#   }
#   #tooltip {
#     position: fixed;
#     pointer-events: none;
#     background: rgba(15,17,23,.93);
#     border: 1px solid #2e3350;
#     border-radius: 7px;
#     padding: 9px 13px;
#     font-size: .82rem;
#     color: #e8eaf0;
#     max-width: 280px;
#     line-height: 1.55;
#     display: none;
#     z-index: 9999;
#     box-shadow: 0 4px 18px rgba(0,0,0,.55);
#   }
#   #tooltip strong { color: #7eb8f7; }
#   .legend-wrap {
#     display: flex;
#     gap: 22px;
#     justify-content: center;
#     margin-top: 14px;
#     flex-wrap: wrap;
#   }
#   .legend-item {
#     display: flex;
#     align-items: center;
#     gap: 7px;
#     font-size: .83rem;
#     color: #a8b0cc;
#   }
#   .legend-swatch {
#     width: 14px; height: 14px;
#     border-radius: 3px;
#     flex-shrink: 0;
#   }
#   #no-data {
#     margin-top: 80px;
#     font-size: 1.1rem;
#     color: #6b7494;
#     text-align: center;
#   }
# </style>
# </head>
# <body>
# <h1>__TITLE__</h1>
# <div id="subtitle">__SUBTITLE__</div>
# <div id="chart-wrap"><svg id="chord-svg"></svg></div>
# <div class="legend-wrap" id="legend"></div>
# <div id="tooltip"></div>
# <div id="no-data" style="display:none">No data to display.</div>

# <script>
# (function () {
#   "use strict";

#   const names   = __NAMES__;
#   const matrix  = __MATRIX__;
#   const groups  = __GROUPS__;
#   const isReflexive = __IS_REFLEXIVE__;
#   const srcLabel = __SRC_LABEL__;
#   const tgtLabel = __TGT_LABEL__;

#   const N = names.length;

#   // ── Degenerate guard ──────────────────────────────────────────────────────
#   if (N === 0 || matrix.length === 0) {
#     document.getElementById("no-data").style.display = "block";
#     document.getElementById("chart-wrap").style.display = "none";
#     return;
#   }

#   // Check that at least one cell is non-zero
#   const hasData = matrix.some(function(row) { return row.some(function(v) { return v > 0; }); });
#   if (!hasData) {
#     document.getElementById("no-data").style.display = "block";
#     document.getElementById("chart-wrap").style.display = "none";
#     return;
#   }

#   // ── Dimensions ────────────────────────────────────────────────────────────
#   const labelPad   = Math.min(120, Math.max(70, Math.ceil(d3.max(names, function(d) { return d.length; }) * 6.5)));
#   const size        = Math.max(520, Math.min(900, N * 18 + 300));
#   const width       = size;
#   const height      = size;
#   const outerRadius = size / 2 - labelPad;
#   const innerRadius = outerRadius - 22;

#   // ── Colour scales ─────────────────────────────────────────────────────────
#   let colourOf;
#   if (isReflexive) {
#     const scale = d3.scaleSequential(d3.interpolateRainbow).domain([0, N]);
#     colourOf = function(i) { return scale(i); };
#   } else {
#     // Two-group colouring: blues for group 0, oranges for group 1
#     const blueScale   = d3.scaleSequential(d3.interpolateBlues).domain([-0.5, N + 0.5]);
#     const orangeScale = d3.scaleSequential(d3.interpolateOranges).domain([-0.5, N + 0.5]);
#     colourOf = function(i) {
#       return groups[i] === 0 ? blueScale(i + 1) : orangeScale(i + 1);
#     };
#   }

#   // ── Chord layout ──────────────────────────────────────────────────────────
#   const chord = d3.chord()
#     .padAngle(Math.max(0.01, Math.min(0.04, 2 / N)))
#     .sortSubgroups(d3.descending);

#   const chords = chord(matrix);

#   // ── SVG ───────────────────────────────────────────────────────────────────
#   const svg = d3.select("#chord-svg")
#     .attr("width",  width)
#     .attr("height", height)
#     .attr("viewBox", "0 0 " + width + " " + height);

#   const g = svg.append("g")
#     .attr("transform", "translate(" + (width / 2) + "," + (height / 2) + ")");

#   // ── Tooltip ───────────────────────────────────────────────────────────────
#   const tooltip = d3.select("#tooltip");

#   function showTip(html, event) {
#     tooltip
#       .style("display", "block")
#       .html(html);
#     moveTip(event);
#   }
#   function moveTip(event) {
#     const tw = tooltip.node().offsetWidth;
#     const th = tooltip.node().offsetHeight;
#     let x = event.clientX + 14;
#     let y = event.clientY - 10;
#     if (x + tw > window.innerWidth  - 8) { x = event.clientX - tw - 14; }
#     if (y + th > window.innerHeight - 8) { y = event.clientY - th - 10; }
#     tooltip.style("left", x + "px").style("top", y + "px");
#   }
#   function hideTip() { tooltip.style("display", "none"); }

#   // ── Arc generator ─────────────────────────────────────────────────────────
#   const arc = d3.arc()
#     .innerRadius(innerRadius)
#     .outerRadius(outerRadius);

#   // ── Ribbon generator ──────────────────────────────────────────────────────
#   const ribbon = d3.ribbon().radius(innerRadius);

#   // ── Draw ribbons ──────────────────────────────────────────────────────────
#   const ribbonG = g.append("g").attr("class", "ribbons");

#   const ribbonPaths = ribbonG.selectAll("path")
#     .data(chords)
#     .join("path")
#       .attr("class", "ribbon")
#       .attr("d", ribbon)
#       .attr("fill", function(d) { return colourOf(d.source.index); })
#       .attr("stroke", function(d) { return d3.color(colourOf(d.source.index)).darker(0.5); })
#       .attr("stroke-width", 0.5);

#   // ── Draw group arcs ───────────────────────────────────────────────────────
#   const groupG = g.append("g").attr("class", "groups");

#   const groupArcs = groupG.selectAll("g")
#     .data(chords.groups)
#     .join("g")
#       .attr("class", "group-arc");

#   groupArcs.append("path")
#     .attr("d", arc)
#     .attr("fill", function(d) { return colourOf(d.index); })
#     .attr("stroke", function(d) { return d3.color(colourOf(d.index)).darker(0.6); })
#     .attr("stroke-width", 0.8);

#   // ── Labels ────────────────────────────────────────────────────────────────
#   groupArcs.append("text")
#     .attr("class", "chord-label")
#     .each(function(d) { d.angle = (d.startAngle + d.endAngle) / 2; })
#     .attr("dy", "0.35em")
#     .attr("transform", function(d) {
#       const rotate = (d.angle * 180 / Math.PI - 90);
#       const flip   = d.angle > Math.PI;
#       return "rotate(" + rotate + ")"
#            + " translate(" + (outerRadius + 8) + ",0)"
#            + (flip ? " rotate(180)" : "");
#     })
#     .attr("text-anchor", function(d) { return d.angle > Math.PI ? "end" : "start"; })
#     .text(function(d) { return names[d.index]; });

#   // ── Interactions ──────────────────────────────────────────────────────────
#   function fadeAll() {
#     ribbonPaths.classed("faded", true).classed("highlighted", false);
#     groupArcs.classed("faded", true);
#   }
#   function restoreAll() {
#     ribbonPaths.classed("faded", false).classed("highlighted", false);
#     groupArcs.classed("faded", false);
#   }

#   // Group arc hover
#   groupArcs
#     .on("mouseover", function(event, d) {
#       fadeAll();
#       // Highlight this arc
#       d3.select(this).classed("faded", false);
#       // Highlight connected ribbons and their partner arcs
#       ribbonPaths
#         .filter(function(r) {
#           return r.source.index === d.index || r.target.index === d.index;
#         })
#         .classed("faded", false)
#         .classed("highlighted", true)
#         .each(function(r) {
#           const partner = r.source.index === d.index ? r.target.index : r.source.index;
#           groupArcs.filter(function(g2) { return g2.index === partner; }).classed("faded", false);
#         });

#       // Tooltip: sum of widths for this node
#       const total = matrix[d.index].reduce(function(a, b) { return a + b; }, 0);
#       showTip(
#         "<strong>" + names[d.index] + "</strong><br/>"
#         + "Total flow: <strong>" + d3.format(",.2~f")(total / 2) + "</strong>",
#         event
#       );
#     })
#     .on("mousemove", moveTip)
#     .on("mouseout", function() { restoreAll(); hideTip(); });

#   // Ribbon hover
#   ribbonPaths
#     .on("mouseover", function(event, d) {
#       fadeAll();
#       d3.select(this).classed("faded", false).classed("highlighted", true);
#       groupArcs.filter(function(g2) {
#         return g2.index === d.source.index || g2.index === d.target.index;
#       }).classed("faded", false);

#       const srcName = names[d.source.index];
#       const tgtName = names[d.target.index];
#       const val     = matrix[d.source.index][d.target.index];
#       showTip(
#         "<strong>" + srcName + "</strong>"
#         + " ↔ "
#         + "<strong>" + tgtName + "</strong><br/>"
#         + "Value: <strong>" + d3.format(",.2~f")(val) + "</strong>",
#         event
#       );
#     })
#     .on("mousemove", moveTip)
#     .on("mouseout", function() { restoreAll(); hideTip(); });

#   // ── Legend (bipartite only) ───────────────────────────────────────────────
#   if (!isReflexive) {
#     const legendWrap = d3.select("#legend");

#     const swatchSrc = colourOf(0);
#     // Find first node in group 1
#     let swatchTgt = "#aaa";
#     for (let i = 0; i < N; i++) {
#       if (groups[i] === 1) { swatchTgt = colourOf(i); break; }
#     }

#     legendWrap.append("div").attr("class", "legend-item").html(
#       '<div class="legend-swatch" style="background:' + swatchSrc + '"></div>'
#       + '<span>' + srcLabel + '</span>'
#     );
#     legendWrap.append("div").attr("class", "legend-item").html(
#       '<div class="legend-swatch" style="background:' + swatchTgt + '"></div>'
#       + '<span>' + tgtLabel + '</span>'
#     );
#   }

# })();
# </script>
# </body>
# </html>
# '''


# # ---------------------------------------------------------------------------
# # render()
# # ---------------------------------------------------------------------------

# def render(mapping: dict, rows: list) -> str:
#     source_col = mapping["source"]
#     target_col = mapping["target"]
#     width_col  = mapping["width"]
#     pattern    = mapping.get("pattern", None)
#     title_raw  = mapping.get("title", "Chord Diagram")
#     title_esc  = html.escape(str(title_raw))

#     # Labels for the two entity sets (bipartite legend)
#     src_label = html.escape(str(mapping.get("source_label", source_col)))
#     tgt_label = html.escape(str(mapping.get("target_label", target_col)))

#     # Build matrix
#     names, matrix, groups = build_matrix(rows, source_col, target_col, width_col, pattern)

#     n = len(names)

#     # Infer final pattern for JS flag
#     if pattern is None:
#         src_set = set(str(r[source_col]) for r in rows if r.get(source_col) is not None)
#         tgt_set = set(str(r[target_col]) for r in rows if r.get(target_col) is not None)
#         is_reflexive = not src_set.isdisjoint(tgt_set)
#     else:
#         is_reflexive = (pattern == "reflexive_many_many_relationship")

#     subtitle = (
#         "Reflexive chord diagram — " + str(n) + " instances"
#         if is_reflexive else
#         "Bipartite chord diagram — " + str(n) + " instances"
#     )

#     def safe_json(obj):
#         return json.dumps(obj).replace("</", "<\\/")

#     names_json      = safe_json([html.escape(str(nm)) for nm in names])
#     matrix_json     = safe_json(matrix)
#     groups_json     = safe_json(groups)
#     is_ref_json     = "true" if is_reflexive else "false"
#     src_label_json  = safe_json(src_label)
#     tgt_label_json  = safe_json(tgt_label)

#     html_out = TEMPLATE
#     html_out = html_out.replace("__TITLE__",       title_esc)
#     html_out = html_out.replace("__SUBTITLE__",    html.escape(subtitle))
#     html_out = html_out.replace("__NAMES__",       names_json)
#     html_out = html_out.replace("__MATRIX__",      matrix_json)
#     html_out = html_out.replace("__GROUPS__",      groups_json)
#     html_out = html_out.replace("__IS_REFLEXIVE__", is_ref_json)
#     html_out = html_out.replace("__SRC_LABEL__",   src_label_json)
#     html_out = html_out.replace("__TGT_LABEL__",   tgt_label_json)

#     return html_out


# # ---------------------------------------------------------------------------
# # CLI
# # ---------------------------------------------------------------------------

# def main():
#     parser = argparse.ArgumentParser(description="Chord diagram renderer")
#     parser.add_argument("--mapping", required=True, help="Path to mapping JSON file")
#     parser.add_argument("--data",    required=True, help="Path to data JSON file")
#     parser.add_argument("--out",     required=True, help="Output HTML file path")
#     args = parser.parse_args()

#     mapping_path = pathlib.Path(args.mapping)
#     data_path    = pathlib.Path(args.data)
#     out_path     = pathlib.Path(args.out)

#     with mapping_path.open("r", encoding="utf-8") as f:
#         mapping = json.load(f)

#     with data_path.open("r", encoding="utf-8") as f:
#         raw = json.load(f)

#     # Support both a plain array and the grouped Mondial DB format
#     if isinstance(raw, dict) and "tables" in raw:
#         table_name = mapping.get("table", "")
#         rows = raw["tables"].get(table_name, [])
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
