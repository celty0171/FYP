import argparse
import json
import html
import pathlib


def render(mapping: dict, rows: list) -> str:
    # --- Read mapping fields ---
    source_col = mapping["source"]
    target_col = mapping["target"]
    value_col = mapping.get("value") or mapping.get("width") or "count"
    category_col = mapping.get("category")
    pattern = mapping.get("pattern", "")
    title = mapping.get("title", "Adjacency-Matrix Heatmap")

    # --- Filter valid rows ---
    rows = [r for r in rows if r.get(source_col) is not None and r.get(target_col) is not None]

    if not rows:
        escaped_title = html.escape(title)
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>" + escaped_title + "</title></head><body>"
            "<p style='font-family:sans-serif;padding:2em;color:#555'>No data to display.</p>"
            "</body></html>"
        )

    # --- Determine pattern ---
    source_vals = set(str(r[source_col]) for r in rows)
    target_vals = set(str(r[target_col]) for r in rows)

    if pattern == "reflexive_many_many_relationship":
        is_reflexive = True
    elif pattern == "many_many_relationship":
        is_reflexive = False
    else:
        # Infer: if sets are disjoint => bipartite, else reflexive
        is_reflexive = bool(source_vals & target_vals)

    # --- Build node lists ---
    if is_reflexive:
        all_nodes = sorted(source_vals | target_vals)
        row_names = all_nodes
        col_names = all_nodes
    else:
        row_names = sorted(source_vals)
        col_names = sorted(target_vals)

    row_index = {n: i for i, n in enumerate(row_names)}
    col_index = {n: i for i, n in enumerate(col_names)}

    # --- Aggregate cells ---
    # cell_val: (i, j) -> float
    # cell_cat: (i, j) -> {cat: count}
    cell_val = {}
    cell_cat = {}

    for r in rows:
        s = str(r[source_col])
        t = str(r[target_col])

        if is_reflexive:
            if s not in row_index or t not in col_index:
                continue
            i = row_index[s]
            j = col_index[t]
        else:
            if s not in row_index or t not in col_index:
                continue
            i = row_index[s]
            j = col_index[t]

        # weight
        if value_col == "count":
            w = 1.0
        else:
            try:
                w = float(r.get(value_col, 1) or 1)
            except (TypeError, ValueError):
                w = 1.0

        # accumulate
        cell_val[(i, j)] = cell_val.get((i, j), 0.0) + w
        if is_reflexive and i != j:
            cell_val[(j, i)] = cell_val.get((j, i), 0.0) + w

        # category
        if category_col:
            cat = str(r.get(category_col, ""))
            for key in ([(i, j)] + ([(j, i)] if is_reflexive and i != j else [])):
                if key not in cell_cat:
                    cell_cat[key] = {}
                cell_cat[key][cat] = cell_cat[key].get(cat, 0) + 1

    if not cell_val:
        escaped_title = html.escape(title)
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>" + escaped_title + "</title></head><body>"
            "<p style='font-family:sans-serif;padding:2em;color:#555'>No data to display.</p>"
            "</body></html>"
        )

    # --- Build sparse cells list ---
    cells_list = []
    for (i, j), v in sorted(cell_val.items()):
        cell = {"i": i, "j": j, "v": round(v, 6)}
        if category_col and (i, j) in cell_cat:
            dominant = max(cell_cat[(i, j)], key=cell_cat[(i, j)].__getitem__)
            cell["cat"] = html.escape(dominant)
        cells_list.append(cell)

    max_val = max(c["v"] for c in cells_list) if cells_list else 1

    # --- Escape labels ---
    row_names_escaped = [html.escape(n) for n in row_names]
    col_names_escaped = [html.escape(n) for n in col_names]

    # --- Serialize to JSON (script-safe) ---
    def safe_json(obj):
        return json.dumps(obj).replace("</", "<\\/")

    row_names_json = safe_json(row_names_escaped)
    col_names_json = safe_json(col_names_escaped)
    cells_json = safe_json(cells_list)
    max_val_json = safe_json(max_val)
    value_col_label = html.escape(value_col)
    value_col_json = safe_json(value_col_label)
    category_col_json = safe_json(html.escape(category_col) if category_col else "")
    is_reflexive_json = "true" if is_reflexive else "false"
    title_escaped = html.escape(title)
    subtitle = ("Symmetric adjacency matrix" if is_reflexive else "Bipartite matrix") + \
               " &mdash; colour encodes " + value_col_label
    subtitle_escaped = html.escape(subtitle)

    # --- Build HTML ---
    # Use string concatenation to avoid f-string / .format() brace issues
    html_parts = []
    html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>""" + title_escaped + """</title>
<style>
  body { margin: 0; background: #fafafa; font-family: 'Segoe UI', Arial, sans-serif;
         display: flex; flex-direction: column; align-items: center; }
  #chart-container { display: inline-block; max-width: 100%; overflow: auto; }
  .cell { stroke: #fff; stroke-width: 0.5px; }
  .cell.dimmed { opacity: 0.12; }
  .cell.highlighted { stroke: #333; stroke-width: 1.5px; }
  .row-label, .col-label { font-size: 10px; fill: #333; }
  .row-label.dimmed, .col-label.dimmed { opacity: 0.25; }
  .row-label.highlighted, .col-label.highlighted { font-weight: bold; fill: #111; }
  .axis-line { stroke: #ccc; stroke-width: 1px; }
  #tooltip {
    position: absolute; pointer-events: none; background: rgba(30,30,30,0.88);
    color: #fff; padding: 7px 11px; border-radius: 5px; font-size: 12px;
    line-height: 1.55; white-space: nowrap; display: none; z-index: 10;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  }
  .legend-label { font-size: 10px; fill: #555; }
  h1 { font-size: 15px; margin: 14px 0 2px 0; color: #222; padding-left: 4px; }
  p.subtitle { font-size: 11px; color: #777; margin: 0 0 6px 0; padding-left: 4px; }
</style>
</head>
<body>
<h1>""" + title_escaped + """</h1>
<p class="subtitle">""" + subtitle_escaped + """</p>
<div id="chart-container"></div>
<div id="tooltip"></div>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
(function() {
  const rowNames = """ + row_names_json + """;
  const colNames = """ + col_names_json + """;
  const cells = """ + cells_json + """;
  const maxVal = """ + max_val_json + """;
  const valueLabel = """ + value_col_json + """;
  const categoryLabel = """ + category_col_json + """;
  const isReflexive = """ + is_reflexive_json + """;

  if (!cells.length) {
    document.getElementById('chart-container').innerHTML =
      '<p style="padding:2em;color:#555">No data to display.</p>';
    return;
  }

  const nRows = rowNames.length;
  const nCols = colNames.length;

  // --- Adaptive cell sizing ---
  // Minimum band size: enough for a readable label (~9px per char, but we cap)
  const MIN_BAND = 14;
  const MAX_BAND = 48;
  const IDEAL_GRID_PX = 560; // target grid dimension

  // Compute band sizes independently per axis
  function bandSize(n) {
    if (n === 0) return MAX_BAND;
    let b = Math.floor(IDEAL_GRID_PX / n);
    if (b < MIN_BAND) b = MIN_BAND;
    if (b > MAX_BAND) b = MAX_BAND;
    return b;
  }

  const bandRow = bandSize(nRows);
  const bandCol = bandSize(nCols);

  const gridW = nCols * bandCol;
  const gridH = nRows * bandRow;

  // --- Label thinning (independent per axis) ---
  function computeStep(n, gridPx, band) {
    // Show every label if band >= 11px, else thin
    if (band >= 11) return 1;
    const maxLabels = Math.max(1, Math.floor(gridPx / 9));
    return Math.max(1, Math.ceil(n / maxLabels));
  }
  const rowStep = computeStep(nRows, gridH, bandRow);
  const colStep = computeStep(nCols, gridW, bandCol);

  // --- Estimate margins from longest labels actually drawn ---
  const CHAR_W = 6.5; // approx px per char at 10px font
  const PAD = 12;

  // Row labels (left margin): longest row label drawn
  let maxRowLabelLen = 0;
  for (let i = 0; i < nRows; i += rowStep) {
    if (rowNames[i].length > maxRowLabelLen) maxRowLabelLen = rowNames[i].length;
  }
  const marginLeft = Math.max(60, maxRowLabelLen * CHAR_W + PAD);

  // Col labels (top margin): longest col label drawn (rotated => length becomes height)
  let maxColLabelLen = 0;
  for (let j = 0; j < nCols; j += colStep) {
    if (colNames[j].length > maxColLabelLen) maxColLabelLen = colNames[j].length;
  }
  const marginTop = Math.max(60, maxColLabelLen * CHAR_W + PAD);

  const marginRight = 20;
  const marginBottom = 60; // space for colour legend

  const svgW = marginLeft + gridW + marginRight;
  const svgH = marginTop + gridH + marginBottom;

  const svg = d3.select('#chart-container')
    .append('svg')
    .attr('width', svgW)
    .attr('height', svgH);

  const g = svg.append('g')
    .attr('transform', 'translate(' + marginLeft + ',' + marginTop + ')');

  // --- Scales ---
  const xScale = d3.scaleBand()
    .domain(d3.range(nCols))
    .range([0, gridW])
    .padding(0.02);

  const yScale = d3.scaleBand()
    .domain(d3.range(nRows))
    .range([0, gridH])
    .padding(0.02);

  const colorScale = d3.scaleSequential(d3.interpolateYlGnBu)
    .domain([0, maxVal]);

  // --- Background grid outline ---
  g.append('rect')
    .attr('x', 0).attr('y', 0)
    .attr('width', gridW).attr('height', gridH)
    .attr('fill', '#f0f0f0').attr('stroke', '#ddd').attr('stroke-width', 1);

  // --- Draw cells ---
  const cellSel = g.selectAll('.cell')
    .data(cells)
    .join('rect')
    .attr('class', 'cell')
    .attr('x', d => xScale(d.j))
    .attr('y', d => yScale(d.i))
    .attr('width', xScale.bandwidth())
    .attr('height', yScale.bandwidth())
    .attr('fill', d => colorScale(d.v))
    .attr('rx', 1).attr('ry', 1);

  // --- Row labels ---
  const rowLabelSel = g.selectAll('.row-label')
    .data(d3.range(nRows))
    .join('text')
    .attr('class', 'row-label')
    .attr('x', -6)
    .attr('y', i => yScale(i) + yScale.bandwidth() / 2)
    .attr('dy', '0.35em')
    .attr('text-anchor', 'end')
    .text(i => (i % rowStep === 0) ? rowNames[i] : '');

  // --- Column labels (rotated) ---
  const colLabelSel = g.selectAll('.col-label')
    .data(d3.range(nCols))
    .join('text')
    .attr('class', 'col-label')
    .attr('transform', j => {
      const x = xScale(j) + xScale.bandwidth() / 2;
      return 'translate(' + x + ',-6) rotate(-60)';
    })
    .attr('dy', '0.35em')
    .attr('text-anchor', 'start')
    .text(j => (j % colStep === 0) ? colNames[j] : '');

  // --- Axis lines ---
  g.append('line').attr('class','axis-line')
    .attr('x1',0).attr('y1',0).attr('x2',gridW).attr('y2',0);
  g.append('line').attr('class','axis-line')
    .attr('x1',0).attr('y1',0).attr('x2',0).attr('y2',gridH);

  // --- Colour legend ---
  const legendW = Math.min(200, gridW);
  const legendH = 12;
  const legendX = 0;
  const legendY = gridH + 28;

  const defs = svg.append('defs');
  const gradId = 'colorGrad';
  const grad = defs.append('linearGradient').attr('id', gradId)
    .attr('x1','0%').attr('x2','100%').attr('y1','0%').attr('y2','0%');
  const nStops = 10;
  for (let k = 0; k <= nStops; k++) {
    grad.append('stop')
      .attr('offset', (k / nStops * 100) + '%')
      .attr('stop-color', colorScale(maxVal * k / nStops));
  }

  const lg = g.append('g').attr('transform', 'translate(' + legendX + ',' + legendY + ')');
  lg.append('rect')
    .attr('width', legendW).attr('height', legendH)
    .attr('fill', 'url(#' + gradId + ')')
    .attr('stroke', '#ccc').attr('stroke-width', 0.5);
  lg.append('text').attr('class','legend-label')
    .attr('x', 0).attr('y', legendH + 12).attr('text-anchor','start')
    .text('0');
  lg.append('text').attr('class','legend-label')
    .attr('x', legendW).attr('y', legendH + 12).attr('text-anchor','end')
    .text(maxVal % 1 === 0 ? maxVal : maxVal.toFixed(2));
  lg.append('text').attr('class','legend-label')
    .attr('x', legendW / 2).attr('y', legendH + 12).attr('text-anchor','middle')
    .text(valueLabel === 'count' ? 'Count' : valueLabel);

  // --- Tooltip ---
  const tooltip = d3.select('#tooltip');

  // --- Interactivity ---
  cellSel
    .on('mouseover', function(event, d) {
      // Highlight row + col, dim rest
      cellSel.classed('dimmed', c => c.i !== d.i && c.j !== d.j)
             .classed('highlighted', c => c === d);
      rowLabelSel.classed('dimmed', i => i !== d.i)
                 .classed('highlighted', i => i === d.i);
      colLabelSel.classed('dimmed', j => j !== d.j)
                 .classed('highlighted', j => j === d.j);

      let html_str = '<strong>' + rowNames[d.i] + '</strong>'
        + (isReflexive ? ' &harr; ' : ' &rarr; ')
        + '<strong>' + colNames[d.j] + '</strong><br>'
        + (valueLabel === 'count' ? 'Count' : valueLabel) + ': '
        + (d.v % 1 === 0 ? d.v : d.v.toFixed(3));
      if (categoryLabel && d.cat !== undefined) {
        html_str += '<br>Dominant ' + categoryLabel + ': ' + d.cat;
      }
      tooltip.style('display', 'block').html(html_str);
    })
    .on('mousemove', function(event) {
      tooltip
        .style('left', (event.pageX + 14) + 'px')
        .style('top', (event.pageY - 28) + 'px');
    })
    .on('mouseout', function() {
      cellSel.classed('dimmed', false).classed('highlighted', false);
      rowLabelSel.classed('dimmed', false).classed('highlighted', false);
      colLabelSel.classed('dimmed', false).classed('highlighted', false);
      tooltip.style('display', 'none');
    });

  // --- BBox refit ---
  try {
    const bb = svg.node().getBBox();
    const pad = 10;
    svg.attr('viewBox', (bb.x - pad) + ' ' + (bb.y - pad) + ' '
      + (bb.width + pad * 2) + ' ' + (bb.height + pad * 2))
      .attr('width', bb.width + pad * 2)
      .attr('height', bb.height + pad * 2);
  } catch(e) { /* getBBox may fail in non-browser env */ }

})();
</script>
</body>
</html>""")

    return "".join(html_parts)


def main():
    parser = argparse.ArgumentParser(description="Adjacency-matrix heatmap renderer")
    parser.add_argument("--mapping", required=True, help="Path to mapping JSON file")
    parser.add_argument("--data", required=True, help="Path to data JSON file")
    parser.add_argument("--out", required=True, help="Output HTML file path")
    args = parser.parse_args()

    mapping_path = pathlib.Path(args.mapping)
    data_path = pathlib.Path(args.data)
    out_path = pathlib.Path(args.out)

    with mapping_path.open("r", encoding="utf-8") as f:
        mapping = json.load(f)

    # Support bare mapping or Stage-1/2 result objects
    if "chart_mapping" in mapping:
        mapping = mapping["chart_mapping"]
    elif "selected_visualisation" in mapping:
        sv = mapping["selected_visualisation"]
        mapping = sv.get("encoding", sv)

    with data_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    # Support grouped Mondial DB or plain array
    if isinstance(raw, dict) and "tables" in raw:
        table_name = mapping.get("table", "")
        rows = raw["tables"].get(table_name, [])
    elif isinstance(raw, list):
        rows = raw
    else:
        rows = []

    html_out = render(mapping, rows)

    with out_path.open("w", encoding="utf-8") as f:
        f.write(html_out)

    print("Written to", out_path)


if __name__ == "__main__":
    main()