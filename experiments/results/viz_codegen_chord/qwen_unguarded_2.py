import argparse
import json
import html
from pathlib import Path

def render(mapping, rows):
    # Extract mapping parameters
    source_col = mapping.get("source")
    target_col = mapping.get("target")
    width_col = mapping.get("width")
    title = mapping.get("title") or "Chord Diagram"

    # Step 1: Determine unique nodes from source and target
    nodes_set = set()
    for row in rows:
        nodes_set.add(row[source_col])
        nodes_set.add(row[target_col])
    nodes_list = sorted(nodes_set)
    node_index_map = {name: idx for idx, name in enumerate(nodes_list)}
    n_nodes = len(nodes_list)

    # Step 2: Initialize matrix
    matrix = [[0.0 for _ in range(n_nodes)] for _ in range(n_nodes)]

    # Step 3: Populate matrix
    for row in rows:
        s = row[source_col]
        t = row[target_col]
        w = float(row[width_col])
        i = node_index_map[s]
        j = node_index_map[t]
        matrix[i][j] += w
        # Assume undirected relationship
        matrix[j][i] += w

    # Prepare data for injection into HTML
    names_json = json.dumps(nodes_list)
    matrix_json = json.dumps(matrix)

    # Generate HTML content
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{
      font-family: sans-serif;
    }}
    svg {{
      display: block;
      margin: auto;
    }}
    .tooltip {{
      position: absolute;
      background: white;
      padding: 5px;
      border: 1px solid black;
      pointer-events: none;
      opacity: 0;
      transition: opacity 0.2s;
    }}
    .tooltip.visible {{
      opacity: 1;
    }}
    .arc text {{
      font-size: 12px;
      pointer-events: none;
    }}
    .arc text.rotate {{
      transform: rotate(-90deg);
    }}
  </style>
</head>
<body>
<svg width="960" height="600"></svg>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const names = {names_json};
const matrix = {matrix_json};

const width = 960;
const height = 600;
const radius = Math.min(width, height) / 2;
const innerRadius = radius * 0.8;

const svg = d3.select("svg")
  .attr("viewBox", [-radius, -radius, width, height]);

const color = d3.scaleOrdinal(d3.schemeCategory10);

const chordLayout = d3.chord()
  .padAngle(0.02)
  .sortSubgroups(d3.descending);

const chords = chordLayout(matrix);

// Draw group arcs
const arc = d3.arc()
  .innerRadius(innerRadius)
  .outerRadius(radius);

const g = svg.append("g");

g.selectAll(".arc")
  .data(chords.groups)
  .enter().append("path")
  .attr("class", "arc")
  .attr("d", arc)
  .style("fill", (d, i) => color(i))
  .on("mouseover", (event, d) => {
    const tooltip = d3.select("#tooltip");
    tooltip.classed("visible", true);
    tooltip.style("left", `${event.pageX + 10}px`)
           .style("top", `${event.pageY + 10}px`);
    
    // Highlight related elements
    d3.selectAll(".arc").style("opacity", 0.2);
    d3.selectAll(".ribbon").style("opacity", 0.2);
    d3.select(event.currentTarget).style("opacity", 1);
    d3.selectAll(`.ribbon[data-source="${d.index}"], .ribbon[data-target="${d.index}"]`).style("opacity", 1);
    
    tooltip.html(`<strong>${html.escape(names[d.index])}</strong><br/>Total: ${d.value.toFixed(2)}`);
  })
  .on("mouseout", () => {
    d3.selectAll(".arc").style("opacity", 1);
    d3.selectAll(".ribbon").style("opacity", 1);
    d3.select("#tooltip").classed("visible", false);
  });

// Add labels
g.selectAll(".label")
  .data(chords.groups)
  .enter().append("text")
  .attr("class", "arc label")
  .attr("transform", d => {
    const angle = (d.startAngle + d.endAngle) / 2;
    return `rotate(${angle * 180 / Math.PI - 90}) translate(${innerRadius + 20}, 0)`;
  })
  .attr("dy", ".35em")
  .text(d => html.escape(names[d.index]))
  .filter(d => (d.startAngle + d.endAngle) / 2 > Math.PI)
  .attr("class", "arc label rotate");

// Draw ribbons
const ribbon = d3.ribbon()
  .radius(innerRadius);

g.selectAll(".ribbon")
  .data(chords)
  .enter().append("path")
  .attr("class", "ribbon")
  .attr("d", ribbon)
  .style("fill", d => color(d.source.index))
  .on("mouseover", (event, d) => {
    const tooltip = d3.select("#tooltip");
    tooltip.classed("visible", true);
    tooltip.style("left", `${event.pageX + 10}px`)
           .style("top", `${event.pageY + 10}px`);
    
    // Highlight related elements
    d3.selectAll(".arc").style("opacity", 0.2);
    d3.selectAll(".ribbon").style("opacity", 0.2);
    d3.select(event.currentTarget).style("opacity", 1);
    d3.select(`.arc:nth-child(${d.source.index + 1})`).style("opacity", 1);
    d3.select(`.arc:nth-child(${d.target.index + 1})`).style("opacity", 1);
    
    tooltip.html(`<strong>${html.escape(names[d.source.index])} → ${html.escape(names[d.target.index])}</strong><br/>Value: ${d.value.toFixed(2)}`);
  })
  .on("mouseout", () => {
    d3.selectAll(".arc").style("opacity", 1);
    d3.selectAll(".ribbon").style("opacity", 1);
    d3.select("#tooltip").classed("visible", false);
  });

// Tooltip element
svg.append("div")
  .attr("id", "tooltip")
  .attr("class", "tooltip");
</script>
</body>
</html>
"""

    return html_content


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render a chord diagram based on a mapping and data.")
    parser.add_argument("--mapping", required=True, help="Path to the mapping JSON file.")
    parser.add_argument("--data", required=True, help="Path to the data JSON file.")
    parser.add_argument("--out", required=True, help="Output HTML file path.")
    args = parser.parse_args()

    # Load mapping
    with open(args.mapping, 'r') as f:
        mapping = json.load(f)

    # Load data
    with open(args.data, 'r') as f:
        data_rows = json.load(f)

    # Render HTML
    html_output = render(mapping, data_rows)

    # Write output
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        f.write(html_output)
