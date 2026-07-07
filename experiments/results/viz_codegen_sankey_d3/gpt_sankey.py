import argparse
import json
import html
from pathlib import Path


def _extract_mapping(mapping_obj):
    if not isinstance(mapping_obj, dict):
        raise ValueError("Mapping must be a JSON object.")
    if "chart_mapping" in mapping_obj and isinstance(mapping_obj["chart_mapping"], dict):
        return mapping_obj["chart_mapping"]
    if (
        "selected_visualisation" in mapping_obj
        and isinstance(mapping_obj["selected_visualisation"], dict)
        and "encoding" in mapping_obj["selected_visualisation"]
        and isinstance(mapping_obj["selected_visualisation"]["encoding"], dict)
    ):
        return mapping_obj["selected_visualisation"]["encoding"]
    return mapping_obj


def _extract_rows(data_obj, table_name):
    if isinstance(data_obj, list):
        return data_obj
    if isinstance(data_obj, dict) and "tables" in data_obj and isinstance(data_obj["tables"], dict):
        if table_name not in data_obj["tables"]:
            raise ValueError("Table '" + str(table_name) + "' not found in data['tables'].")
        table_rows = data_obj["tables"][table_name]
        if not isinstance(table_rows, list):
            raise ValueError("Table '" + str(table_name) + "' must be a JSON array of rows.")
        return table_rows
    raise ValueError("Data must be either a JSON array or an object with a 'tables' dictionary.")


def render(mapping: dict, rows: list[dict]) -> str:
    m = _extract_mapping(mapping)

    required = ["table", "source", "target", "width"]
    for k in required:
        if k not in m:
            raise ValueError("Missing required mapping field: " + k)

    source_col = m["source"]
    target_col = m["target"]
    width_col = m["width"]

    title_text = m.get("title", "Sankey Diagram")
    pattern = m.get("pattern")

    src_values = set()
    tgt_values = set()
    link_sums = {}

    for r in rows:
        if not isinstance(r, dict):
            continue
        if source_col not in r or target_col not in r or width_col not in r:
            continue

        src_raw = r[source_col]
        tgt_raw = r[target_col]
        w_raw = r[width_col]

        if src_raw is None or tgt_raw is None or w_raw is None:
            continue

        src_label = str(src_raw)
        tgt_label = str(tgt_raw)

        try:
            w = float(w_raw)
        except (TypeError, ValueError):
            continue

        if w <= 0:
            continue

        src_values.add(src_label)
        tgt_values.add(tgt_label)

        key = (src_label, tgt_label)
        link_sums[key] = link_sums.get(key, 0.0) + w

    if pattern == "reflexive_many_many_relationship":
        subtitle_text = "Link width encodes " + str(width_col) + "; directed flow within the same entity set (source role → target role)."
    elif pattern == "many_many_relationship":
        subtitle_text = "Link width encodes " + str(width_col) + "; flow from source entities to target entities."
    else:
        overlap = len(src_values.intersection(tgt_values)) > 0
        if overlap:
            subtitle_text = "Link width encodes " + str(width_col) + "; directed flow where values may appear on both sides (source role → target role)."
        else:
            subtitle_text = "Link width encodes " + str(width_col) + "; flow from source entities to target entities."

    nodes = []
    for s in sorted(src_values):
        nodes.append(
            {
                "name": "src:" + s,
                "label": html.escape(s),
                "side": "source",
            }
        )
    for t in sorted(tgt_values):
        nodes.append(
            {
                "name": "tgt:" + t,
                "label": html.escape(t),
                "side": "target",
            }
        )

    links = []
    for (s, t), v in link_sums.items():
        links.append(
            {
                "source": "src:" + s,
                "target": "tgt:" + t,
                "value": v,
                "sourceLabel": html.escape(s),
                "targetLabel": html.escape(t),
            }
        )

    title_json = json.dumps(html.escape(str(title_text)))
    subtitle_json = json.dumps(html.escape(str(subtitle_text)))
    nodes_json = json.dumps(nodes, ensure_ascii=False)
    links_json = json.dumps(links, ensure_ascii=False)
    width_label_json = json.dumps(html.escape(str(width_col)))

    template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>__TITLE__</title>
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12/dist/d3-sankey.min.js"></script>
  <style>
    :root {
      --bg: #ffffff;
      --fg: #1f2937;
      --muted: #6b7280;
      --node: #374151;
      --link-base: #94a3b8;
      --dim: 0.12;
      --focus: 0.85;
    }
    html, body {
      margin: 0;
      padding: 0;
      background: var(--bg);
      color: var(--fg);
      font-family: Arial, Helvetica, sans-serif;
    }
    .wrap {
      max-width: 1400px;
      margin: 0 auto;
      padding: 16px 16px 20px 16px;
    }
    h1 {
      margin: 0 0 6px 0;
      font-size: 22px;
      line-height: 1.25;
    }
    .subtitle {
      margin: 0 0 10px 0;
      color: var(--muted);
      font-size: 14px;
    }
    .chart-frame {
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      overflow: hidden;
      background: #fff;
    }
    svg {
      display: block;
    }
    .node rect {
      fill: var(--node);
      fill-opacity: 0.9;
      stroke: #111827;
      stroke-width: 0.6px;
      shape-rendering: crispEdges;
    }
    .node text {
      font-size: 12px;
      fill: #111827;
      dominant-baseline: middle;
      pointer-events: none;
    }
    .link {
      fill: none;
      stroke-opacity: 0.5;
      mix-blend-mode: multiply;
    }
    .tooltip {
      position: absolute;
      pointer-events: none;
      background: rgba(17, 24, 39, 0.95);
      color: #f9fafb;
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 12px;
      line-height: 1.35;
      max-width: 340px;
      box-shadow: 0 8px 20px rgba(0,0,0,0.2);
      opacity: 0;
      transition: opacity 80ms linear;
      z-index: 9999;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1 id="title"></h1>
    <p class="subtitle" id="subtitle"></p>
    <div class="chart-frame" id="chart"></div>
  </div>
  <div id="tooltip" class="tooltip"></div>

  <script>
    const TITLE = __TITLE__;
    const SUBTITLE = __SUBTITLE__;
    const WIDTH_LABEL = __WIDTH_LABEL__;
    const BASE_NODES = __NODES__;
    const BASE_LINKS = __LINKS__;

    document.getElementById("title").textContent = TITLE;
    document.getElementById("subtitle").textContent = SUBTITLE;

    const sourceCount = BASE_NODES.filter(d => d.side === "source").length;
    const targetCount = BASE_NODES.filter(d => d.side === "target").length;
    const maxCount = Math.max(sourceCount, targetCount, 1);

    const margin = { top: 16, right: 220, bottom: 16, left: 220 };
    const innerWidth = 1100;
    const innerHeight = Math.max(520, maxCount * 22 + 140);
    const width = innerWidth + margin.left + margin.right;
    const height = innerHeight + margin.top + margin.bottom;

    const svg = d3.select("#chart")
      .append("svg")
      .attr("width", width)
      .attr("height", height);

    const g = svg.append("g").attr("transform", "translate(" + margin.left + "," + margin.top + ")");

    const tooltip = d3.select("#tooltip");

    function showTooltip(event, htmlContent) {
      tooltip
        .style("opacity", 1)
        .html(htmlContent)
        .style("left", (event.pageX + 14) + "px")
        .style("top", (event.pageY + 14) + "px");
    }

    function moveTooltip(event) {
      tooltip
        .style("left", (event.pageX + 14) + "px")
        .style("top", (event.pageY + 14) + "px");
    }

    function hideTooltip() {
      tooltip.style("opacity", 0);
    }

    function sanitizeNumber(x) {
      const n = Number(x);
      return Number.isFinite(n) ? n : 0;
    }

    const sourceToTargets = new Map();
    const targetIncoming = new Map();

    for (const l of BASE_LINKS) {
      const s = l.source;
      const t = l.target;
      const v = sanitizeNumber(l.value);
      if (!sourceToTargets.has(s)) sourceToTargets.set(s, new Map());
      const m = sourceToTargets.get(s);
      m.set(t, (m.get(t) || 0) + v);
      targetIncoming.set(t, (targetIncoming.get(t) || 0) + v);
    }

    const targetNames = BASE_NODES.filter(d => d.side === "target").map(d => d.name);
    const sourceNames = BASE_NODES.filter(d => d.side === "source").map(d => d.name);

    const aff = new Map();
    for (const t1 of targetNames) {
      const row = new Map();
      for (const t2 of targetNames) row.set(t2, 0);
      aff.set(t1, row);
    }

    for (const s of sourceNames) {
      const tm = sourceToTargets.get(s) || new Map();
      const entries = Array.from(tm.entries());
      for (let i = 0; i < entries.length; i += 1) {
        for (let j = i; j < entries.length; j += 1) {
          const ti = entries[i][0];
          const wi = entries[i][1];
          const tj = entries[j][0];
          const wj = entries[j][1];
          const inc = Math.min(wi, wj);
          aff.get(ti).set(tj, (aff.get(ti).get(tj) || 0) + inc);
          if (ti !== tj) {
            aff.get(tj).set(ti, (aff.get(tj).get(ti) || 0) + inc);
          }
        }
      }
    }

    const targetLabelByName = new Map(BASE_NODES.filter(d => d.side === "target").map(d => [d.name, d.label]));
    const targetInfo = targetNames.map(t => ({
      name: t,
      incoming: targetIncoming.get(t) || 0,
      label: targetLabelByName.get(t) || t
    }));

    targetInfo.sort((a, b) => {
      if (b.incoming !== a.incoming) return b.incoming - a.incoming;
      return a.label.localeCompare(b.label);
    });

    const orderedTargets = [];
    const unvisited = new Set(targetInfo.map(d => d.name));

    if (targetInfo.length > 0) {
      let current = targetInfo[0].name;
      orderedTargets.push(current);
      unvisited.delete(current);

      while (unvisited.size > 0) {
        const candidates = Array.from(unvisited);
        candidates.sort((a, b) => {
          const aa = aff.get(current) ? (aff.get(current).get(a) || 0) : 0;
          const bb = aff.get(current) ? (aff.get(current).get(b) || 0) : 0;
          if (bb !== aa) return bb - aa;
          const ina = targetIncoming.get(a) || 0;
          const inb = targetIncoming.get(b) || 0;
          if (inb !== ina) return inb - ina;
          const la = targetLabelByName.get(a) || a;
          const lb = targetLabelByName.get(b) || b;
          return la.localeCompare(lb);
        });
        current = candidates[0];
        orderedTargets.push(current);
        unvisited.delete(current);
      }
    }

    const targetRank = new Map();
    orderedTargets.forEach((t, i) => targetRank.set(t, i));

    const sourceLabelByName = new Map(BASE_NODES.filter(d => d.side === "source").map(d => [d.name, d.label]));
    const sourceMetrics = sourceNames.map(s => {
      const tm = sourceToTargets.get(s) || new Map();
      let total = 0;
      let weighted = 0;
      for (const [t, w] of tm.entries()) {
        const r = targetRank.has(t) ? targetRank.get(t) : 0;
        total += w;
        weighted += w * r;
      }
      const bary = total > 0 ? weighted / total : 0;
      return {
        name: s,
        bary: bary,
        total: total,
        label: sourceLabelByName.get(s) || s
      };
    });

    sourceMetrics.sort((a, b) => {
      if (a.bary !== b.bary) return a.bary - b.bary;
      if (b.total !== a.total) return b.total - a.total;
      return a.label.localeCompare(b.label);
    });

    const sourceRank = new Map();
    sourceMetrics.forEach((s, i) => sourceRank.set(s.name, i));

    const nodes = BASE_NODES.map(d => {
      const copy = {
        name: d.name,
        label: d.label,
        side: d.side
      };
      if (d.side === "source") {
        copy.order = sourceRank.has(d.name) ? sourceRank.get(d.name) : 0;
      } else {
        copy.order = targetRank.has(d.name) ? targetRank.get(d.name) : 0;
      }
      return copy;
    });

    const links = BASE_LINKS.map(d => ({
      source: d.source,
      target: d.target,
      value: sanitizeNumber(d.value),
      sourceLabel: d.sourceLabel,
      targetLabel: d.targetLabel
    }));

    links.sort((a, b) => a.value - b.value);

    const color = d3.scaleOrdinal(d3.schemeTableau10).domain(orderedTargets);

    const sankey = d3.sankey()
      .nodeId(d => d.name)
      .nodeWidth(14)
      .nodePadding(14)
      .nodeSort((a, b) => d3.ascending(a.order, b.order))
      .linkSort((a, b) => (a.target.order - b.target.order) || (a.source.order - b.source.order))
      .nodeAlign(d3.sankeyLeft)
      .iterations(64)
      .extent([[0, 0], [innerWidth, innerHeight]]);

    const graph = sankey({
      nodes: nodes.map(d => Object.assign({}, d)),
      links: links.map(d => Object.assign({}, d))
    });

    const link = g.append("g")
      .attr("fill", "none")
      .selectAll("path")
      .data(graph.links)
      .join("path")
      .attr("class", "link")
      .attr("d", d3.sankeyLinkHorizontal())
      .attr("stroke", d => color(d.target.name))
      .attr("stroke-width", d => Math.max(1, d.width))
      .attr("stroke-opacity", 0.52)
      .on("mouseover", (event, d) => {
        link.attr("stroke-opacity", l => l === d ? 0.9 : 0.08);
        node.attr("opacity", n => (n === d.source || n === d.target) ? 1 : 0.25);

        const val = d3.format(",.3~f")(d.value);
        showTooltip(event, "<div><strong>" + d.source.label + " → " + d.target.label + "</strong></div><div>" + WIDTH_LABEL + ": " + val + "</div>");
      })
      .on("mousemove", (event) => {
        moveTooltip(event);
      })
      .on("mouseout", () => {
        link.attr("stroke-opacity", 0.52);
        node.attr("opacity", 1);
        hideTooltip();
      });

    const node = g.append("g")
      .selectAll("g")
      .data(graph.nodes)
      .join("g")
      .attr("class", "node");

    node.append("rect")
      .attr("x", d => d.x0)
      .attr("y", d => d.y0)
      .attr("height", d => Math.max(1, d.y1 - d.y0))
      .attr("width", d => d.x1 - d.x0)
      .on("mouseover", (event, d) => {
        link.attr("stroke-opacity", l => (l.source === d || l.target === d) ? 0.88 : 0.06);
        node.attr("opacity", n => n === d ? 1 : 0.35);

        const totalFlow = d3.sum(graph.links, l => (l.source === d || l.target === d) ? l.value : 0);
        const val = d3.format(",.3~f")(totalFlow);
        showTooltip(event, "<div><strong>" + d.label + "</strong></div><div>Total flow: " + val + "</div>");
      })
      .on("mousemove", (event) => {
        moveTooltip(event);
      })
      .on("mouseout", () => {
        link.attr("stroke-opacity", 0.52);
        node.attr("opacity", 1);
        hideTooltip();
      });

    node.append("text")
      .attr("x", d => d.x0 < innerWidth / 2 ? d.x1 + 8 : d.x0 - 8)
      .attr("y", d => (d.y0 + d.y1) / 2)
      .attr("text-anchor", d => d.x0 < innerWidth / 2 ? "start" : "end")
      .text(d => d.label);
  </script>
</body>
</html>
"""
    return (
        template
        .replace("__TITLE__", title_json)
        .replace("__SUBTITLE__", subtitle_json)
        .replace("__WIDTH_LABEL__", width_label_json)
        .replace("__NODES__", nodes_json)
        .replace("__LINKS__", links_json)
    )


def main():
    parser = argparse.ArgumentParser(description="Render a Sankey diagram HTML from mapping and data JSON.")
    parser.add_argument("--mapping", required=True, help="Path to mapping JSON file")
    parser.add_argument("--data", required=True, help="Path to data JSON file")
    parser.add_argument("--out", required=True, help="Path to output HTML file")
    args = parser.parse_args()

    mapping_path = Path(args.mapping)
    data_path = Path(args.data)
    out_path = Path(args.out)

    with mapping_path.open("r", encoding="utf-8") as f:
        mapping_obj = json.load(f)

    mapping = _extract_mapping(mapping_obj)

    if "table" not in mapping:
        raise ValueError("Mapping must include 'table'.")

    with data_path.open("r", encoding="utf-8") as f:
        data_obj = json.load(f)

    rows = _extract_rows(data_obj, mapping["table"])
    html_doc = render(mapping, rows)

    out_path.write_text(html_doc, encoding="utf-8")


if __name__ == "__main__":
    main()