import argparse
import json
import html
import pathlib


def render(mapping: dict, rows: list[dict]) -> str:
    source_col = mapping["source"]
    target_col = mapping["target"]
    width_col = mapping["width"]
    title = mapping.get("title", "Chord Diagram")
    pattern = mapping.get("pattern", "")

    # ------------------------------------------------------------------ #
    # 1. Collect all source and target values                             #
    # ------------------------------------------------------------------ #
    all_sources_set = set()
    all_targets_set = set()
    for row in rows:
        sv = row.get(source_col)
        tv = row.get(target_col)
        if sv is not None:
            all_sources_set.add(str(sv))
        if tv is not None:
            all_targets_set.add(str(tv))

    # Infer pattern if not supplied
    if not pattern:
        if all_sources_set.isdisjoint(all_targets_set):
            pattern = "many_many_relationship"
        else:
            pattern = "reflexive_many_many_relationship"

    is_bipartite = (pattern == "many_many_relationship")

    # ------------------------------------------------------------------ #
    # 2. Build ordered node list                                          #
    # ------------------------------------------------------------------ #
    if is_bipartite:
        # E1 (sources) first, sorted; then E2 (targets) sorted
        # Nodes that appear in both sets are placed in the source group
        e1_nodes = sorted(all_sources_set)
        e2_nodes = sorted(all_targets_set - all_sources_set)
        names_raw = e1_nodes + e2_nodes
        # group membership: 0 = source/E1, 1 = target/E2
        group_of = {}
        for n in e1_nodes:
            group_of[n] = 0
        for n in e2_nodes:
            group_of[n] = 1
    else:
        # Reflexive: union of both sides, sorted
        names_raw = sorted(all_sources_set | all_targets_set)
        group_of = {n: 0 for n in names_raw}

    n = len(names_raw)
    idx_of = {name: i for i, name in enumerate(names_raw)}

    # ------------------------------------------------------------------ #
    # 3. Build N×N matrix                                                #
    # ------------------------------------------------------------------ #
    matrix = [[0.0] * n for _ in range(n)]

    for row in rows:
        sv = row.get(source_col)
        tv = row.get(target_col)
        if sv is None or tv is None:
            continue
        sv = str(sv)
        tv = str(tv)
        if sv not in idx_of or tv not in idx_of:
            continue
        try:
            w = float(row[width_col]) if row.get(width_col) is not None else 0.0
        except (ValueError, TypeError):
            w = 0.0
        if w <= 0:
            continue
        i = idx_of[sv]
        j = idx_of[tv]
        matrix[i][j] += w
        if i != j:
            matrix[j][i] += w

    # ------------------------------------------------------------------ #
    # 4. Escape labels for safe HTML/JS embedding                        #
    # ------------------------------------------------------------------ #
    names_escaped = [html.escape(name) for name in names_raw]
    groups_list = [group_of[name] for name in names_raw]

    title_escaped = html.escape(title)
    source_col_escaped = html.escape(str(source_col))
    target_col_escaped = html.escape(str(target_col))
    width_col_escaped = html.escape(str(width_col))

    # Subtitle
    if is_bipartite:
        subtitle_escaped = (
            html.escape("Ribbon width = " + str(width_col)) +
            " &middot; " +
            "<em>" + source_col_escaped + "</em>" +
            " &harr; " +
            "<em>" + target_col_escaped + "</em>"
        )
    else:
        subtitle_escaped = (
            html.escape("Ribbon width = " + str(width_col)) +
            " &middot; Reflexive relationships within <em>" +
            source_col_escaped + "</em>"
        )

    # ------------------------------------------------------------------ #
    # 5. Serialise for injection                                          #
    # ------------------------------------------------------------------ #
    names_json = json.dumps(names_escaped)
    matrix_json = json.dumps(matrix)
    groups_json = json.dumps(groups_list)
    is_bipartite_json = json.dumps(is_bipartite)
    e1_label_json = json.dumps(source_col_escaped)
    e2_label_json = json.dumps(target_col_escaped)
    width_col_json = json.dumps(width_col_escaped)

    # ------------------------------------------------------------------ #
    # 6. Compute SVG dimensions                                           #
    # ------------------------------------------------------------------ #
    # Give more height for larger node counts
    base_dim = max(700, min(1100, 500 + n * 8))
    svg_w = base_dim
    svg_h = base_dim

    # ------------------------------------------------------------------ #
    # 7. Build HTML via string concatenation (no f-strings / .format)    #
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
    padding: 20px 10px;
    overflow: auto;
    display: inline-block;
    min-width: 100%;
  }
  svg { display: block; margin: 0 auto; }
  .group-arc { cursor: pointer; }
  .group-arc path { stroke: #fff; stroke-width: 1.5px; }
  .ribbon { fill-opacity: 0.55; cursor: pointer; transition: fill-opacity 0.15s; }
  .ribbon.dimmed { fill-opacity: 0.04; }
  .ribbon.highlighted { fill-opacity: 0.82; }
  .group-arc.dimmed path { opacity: 0.2; }
  .group-arc.dimmed text { opacity: 0.2; }
  .chord-label {
    font-size: 11px;
    fill: #222;
    pointer-events: none;
    dominant-baseline: middle;
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
  .legend {
    margin-top: 14px;
    display: flex;
    flex-wrap: wrap;
    gap: 10px 22px;
    font-size: 12px;
    color: #444;
    padding-left: 8px;
    justify-content: center;
  }
  .legend-item { display: flex; align-items: center; gap: 6px; }
  .legend-swatch {
    width: 18px; height: 12px; border-radius: 3px; flex-shrink: 0;
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
  <svg id="chord-svg"></svg>
  <div class="legend" id="legend"></div>
</div>
<div id="tooltip"></div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
(function () {
  "use strict";

  // ---- injected data ----
  const NAMES       = """ + names_json + """;
  const MATRIX      = """ + matrix_json + """;
  const GROUPS      = """ + groups_json + """;
  const IS_BIPARTITE = """ + is_bipartite_json + """;
  const E1_LABEL    = """ + e1_label_json + """;
  const E2_LABEL    = """ + e2_label_json + """;
  const WIDTH_COL   = """ + width_col_json + """;
  const SVG_W       = """ + str(svg_w) + """;
  const SVG_H       = """ + str(svg_h) + """;

  const N = NAMES.length;

  // ---- geometry ----
  const labelPad   = 28;
  const outerRadius = Math.min(SVG_W, SVG_H) / 2 - labelPad - 60;
  const innerRadius = outerRadius - 22;

  // ---- colour scales ----
  // Reflexive: one colour per node (tableau + schemeSet3 extended)
  const reflexiveColours = d3.quantize(d3.interpolateRainbow, Math.max(N, 2));

  // Bipartite: blues family for E1, oranges/reds for E2
  const e1Count = GROUPS.filter(g => g === 0).length;
  const e2Count = GROUPS.filter(g => g === 1).length;
  const e1Colours = d3.quantize(
    t => d3.interpolateBlues(0.35 + 0.55 * t), Math.max(e1Count, 2)
  );
  const e2Colours = d3.quantize(
    t => d3.interpolateOranges(0.35 + 0.55 * t), Math.max(e2Count, 2)
  );

  // Per-node colour
  let e1Ptr = 0, e2Ptr = 0;
  const nodeColour = NAMES.map((_, i) => {
    if (!IS_BIPARTITE) return reflexiveColours[i % reflexiveColours.length];
    if (GROUPS[i] === 0) return e1Colours[e1Ptr++ % e1Colours.length];
    return e2Colours[e2Ptr++ % e2Colours.length];
  });

  // ---- chord layout ----
  const chordLayout = d3.chord()
    .padAngle(Math.max(0.01, Math.min(0.04, 2 / Math.max(N, 1))))
    .sortSubgroups(d3.descending);

  const chords = chordLayout(MATRIX);

  // ---- SVG ----
  const svg = d3.select("#chord-svg")
    .attr("width",  SVG_W)
    .attr("height", SVG_H);

  const g = svg.append("g")
    .attr("transform", "translate(" + (SVG_W / 2) + "," + (SVG_H / 2) + ")");

  // ---- tooltip ----
  const tooltip = d3.select("#tooltip");
  function showTip(content) {
    tooltip.style("display", "block").html(content);
  }
  function moveTip(event) {
    tooltip
      .style("left", (event.clientX + 14) + "px")
      .style("top",  (event.clientY - 10) + "px");
  }
  function hideTip() { tooltip.style("display", "none"); }

  // ---- arc generator ----
  const arcGen = d3.arc()
    .innerRadius(innerRadius)
    .outerRadius(outerRadius);

  // ---- ribbon generator ----
  const ribbonGen = d3.ribbon().radius(innerRadius);

  // ---- draw ribbons ----
  const ribbonSel = g.append("g")
    .attr("class", "ribbons")
    .selectAll("path")
    .data(chords)
    .join("path")
      .attr("class", "ribbon")
      .attr("d", ribbonGen)
      .attr("fill", d => nodeColour[d.target.index])
      .attr("stroke", d => d3.color(nodeColour[d.target.index]).darker(0.5))
      .attr("stroke-width", 0.5)
      .on("mouseover", function (event, d) {
        const srcName = NAMES[d.source.index];
        const tgtName = NAMES[d.target.index];
        const val = d.source.value.toLocaleString(
          undefined, { maximumFractionDigits: 2 }
        );
        showTip(
          "<strong>" + srcName + "</strong>" +
          " &harr; <strong>" + tgtName + "</strong>" +
          "<br/>" + WIDTH_COL + ": <strong>" + val + "</strong>"
        );
        moveTip(event);
        ribbonSel.classed("dimmed", r =>
          r.source.index !== d.source.index &&
          r.source.index !== d.target.index &&
          r.target.index !== d.source.index &&
          r.target.index !== d.target.index
        );
        ribbonSel.classed("highlighted", r => r === d);
        groupSel.classed("dimmed", grp =>
          grp.index !== d.source.index && grp.index !== d.target.index
        );
      })
      .on("mousemove", moveTip)
      .on("mouseout", function () {
        hideTip();
        ribbonSel.classed("dimmed", false).classed("highlighted", false);
        groupSel.classed("dimmed", false);
      });

  // ---- draw group arcs ----
  const groupSel = g.append("g")
    .attr("class", "groups")
    .selectAll("g")
    .data(chords.groups)
    .join("g")
      .attr("class", "group-arc");

  groupSel.append("path")
    .attr("d", arcGen)
    .attr("fill", d => nodeColour[d.index])
    .attr("stroke", "#fff")
    .attr("stroke-width", 1.5);

  // ---- labels ----
  groupSel.append("text")
    .attr("class", "chord-label")
    .each(function (d) {
      const angle = (d.startAngle + d.endAngle) / 2;
      const rotate = angle * 180 / Math.PI - 90;
      const r = outerRadius + 8;
      const x = Math.sin(angle) * r;
      const y = -Math.cos(angle) * r;
      const flip = angle > Math.PI;
      d3.select(this)
        .attr("transform",
          "translate(" + x + "," + y + ")" +
          " rotate(" + (flip ? rotate + 180 : rotate) + ")"
        )
        .attr("text-anchor", flip ? "end" : "start")
        .text(NAMES[d.index]);
    });

  // ---- group arc interaction ----
  groupSel
    .on("mouseover", function (event, d) {
      const totalFlow = d.value.toLocaleString(
        undefined, { maximumFractionDigits: 2 }
      );
      showTip(
        "<strong>" + NAMES[d.index] + "</strong>" +
        "<br/>Total flow: <strong>" + totalFlow + "</strong>"
      );
      moveTip(event);
      ribbonSel.classed("dimmed", r =>
        r.source.index !== d.index && r.target.index !== d.index
      );
      ribbonSel.classed("highlighted", false);
      groupSel.classed("dimmed", grp => grp.index !== d.index);
    })
    .on("mousemove", moveTip)
    .on("mouseout", function () {
      hideTip();
      ribbonSel.classed("dimmed", false).classed("highlighted", false);
      groupSel.classed("dimmed", false);
    });

  // ---- legend (bipartite only) ----
  if (IS_BIPARTITE) {
    const legendEl = document.getElementById("legend");

    function makeLegendItem(label, colour) {
      const item = document.createElement("div");
      item.className = "legend-item";
      const swatch = document.createElement("div");
      swatch.className = "legend-swatch";
      swatch.style.background = colour;
      const span = document.createElement("span");
      span.textContent = label;
      item.appendChild(swatch);
      item.appendChild(span);
      legendEl.appendChild(item);
    }

    makeLegendItem(E1_LABEL, e1Colours[Math.floor(e1Colours.length / 2)]);
    makeLegendItem(E2_LABEL, e2Colours[Math.floor(e2Colours.length / 2)]);
  }

})();
</script>
</body>
</html>""")

    return "".join(parts)


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="Chord diagram renderer")
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