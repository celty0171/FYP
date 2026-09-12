from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

JS_BODY = """
const margin = {top: 24, right: 20, bottom: 96, left: 56};
const innerW = width - margin.left - margin.right;
const innerH = height - margin.top - margin.bottom;

const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

const x0 = d3.scaleBand().domain(rows.map(d => d.__group)).range([0, innerW]).paddingInner(0.25);
const x1 = d3.scaleBand().domain(segments).range([0, x0.bandwidth()]).padding(0.05);
const maxV = d3.max(rows, d => d3.max(segments, k => d[k] || 0)) || 1;
const y = d3.scaleLinear().domain([0, maxV]).nice().range([innerH, 0]);
const palette = d3.quantize(d3.interpolateRainbow, Math.max(2, segments.length));
const color = d3.scaleOrdinal().domain(segments).range(palette);

g.append("g").call(d3.axisLeft(y).ticks(6));
g.append("g").attr("transform", `translate(0,${innerH})`).call(d3.axisBottom(x0))
  .selectAll("text").attr("transform", "rotate(-40)").style("text-anchor", "end").style("font-size", "9px");

const tip = d3.select("#tip");
// Escape values only where they enter innerHTML (the tooltip); on-canvas labels use .text() and stay raw.
const escHtml = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

const cluster = g.append("g").selectAll("g").data(rows).join("g")
  .attr("transform", d => `translate(${x0(d.__group)},0)`);
const rect = cluster.selectAll("rect")
  .data(d => segments.map(k => ({group: d.__group, key: k, value: d[k] || 0}))).join("rect")
  .attr("x", d => x1(d.key))
  .attr("y", d => y(d.value))
  .attr("width", x1.bandwidth())
  .attr("height", d => innerH - y(d.value))
  .attr("fill", d => color(d.key))
  .attr("fill-opacity", 0.9);

rect
  .on("mouseover", (event, d) => {
    rect.attr("fill-opacity", r => r.key === d.key ? 0.95 : 0.18);
    tip.style("opacity", 1).html("<strong>" + escHtml(d.group) + "</strong><br>" + segmentName + ": " + escHtml(d.key) + "<br>" + valueName + ": " + d.value);
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", () => { rect.attr("fill-opacity", 0.9); tip.style("opacity", 0); });

const legend = d3.select("#legend");
segments.forEach(s => {
  const item = legend.append("span").attr("class", "lg");
  item.append("span").attr("class", "sw").style("background", color(s));
  item.append("span").text(s);
});
"""

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__T__</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  body { font-family: Arial, sans-serif; margin: 16px; }
  h1 { font-size: 18px; margin-bottom: 2px; }
  #sub { color: #555; font-size: 12px; margin: 0 0 8px; }
  #legend { margin: 0 0 8px; font-size: 11px; }
  #legend .lg { display: inline-flex; align-items: center; margin: 0 10px 4px 0; }
  #legend .sw { display: inline-block; width: 11px; height: 11px; border-radius: 2px; margin-right: 4px; }
  .domain, .tick line { stroke: #ccc; }
  #tip { position: absolute; opacity: 0; pointer-events: none; background: rgba(0,0,0,0.82);
         color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px; line-height: 1.4; }
</style>
</head>
<body>
<h1>__T__</h1>
<p id="sub">__SUB__</p>
<div id="legend"></div>
<div id="chart"></div>
<div id="tip"></div>
<script>
"""


def _rows_for(mapping: dict[str, Any], data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        table = mapping.get("table")
        if isinstance(data.get("tables"), dict):
            if not table:
                raise ValueError("data is a grouped database; mapping must name the relation via 'table'")
            return data["tables"][table]
        if table in data:
            return data[table]
    raise ValueError("unsupported data shape: expected a row array or a grouped {'tables': {...}} database")


def render(mapping: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    g_col, s_col, v_col = mapping["group"], mapping["segment"], mapping["value"]
    # A grouped bar gets unreadable fast, so cap to a comparable core (per the paper).
    max_groups = int(mapping.get("max_groups", 12))
    max_segments = int(mapping.get("max_segments", 8))

    groups: list[str] = []
    segments_all: list[str] = []
    cell: dict[tuple[str, str], float] = {}
    seg_groups: dict[str, set[str]] = {}   # segment -> set of groups it appears in (coverage)
    seg_total: dict[str, float] = {}       # segment -> total value (tie-break)
    for r in rows:
        try:
            v = float(r[v_col])
        except (TypeError, ValueError, KeyError):
            continue
        gv, sv = str(r.get(g_col)), str(r.get(s_col))
        if gv not in groups:
            groups.append(gv)
        if sv not in segments_all:
            segments_all.append(sv)
        cell[(gv, sv)] = cell.get((gv, sv), 0.0) + v
        seg_groups.setdefault(sv, set()).add(gv)
        seg_total[sv] = seg_total.get(sv, 0.0) + v

    # Comparable core: the segments shared across the most groups (coverage, tie-broken by total)...
    ranked_segs = sorted(segments_all, key=lambda s: (len(seg_groups[s]), seg_total[s]), reverse=True)
    kept_segs = ranked_segs[:max_segments]
    kept_seg_set = set(kept_segs)
    # ...and the most *complete* groups: those carrying the most of the kept segments (so each
    # cluster has several comparable bars), tie-broken by total value over the kept segments.
    def group_rank(gv: str) -> tuple[int, float]:
        present = sum(1 for s in kept_segs if cell.get((gv, s), 0.0) > 0)
        total = sum(cell.get((gv, s), 0.0) for s in kept_segs)
        return (present, total)
    ranked_groups = sorted(groups, key=group_rank, reverse=True)
    kept_groups = ranked_groups[:max_groups]

    # One row per kept group; every kept segment present (missing = 0). Drop the tail (no "(other)").
    out_rows = []
    for gv in kept_groups:
        row: dict[str, Any] = {"__group": gv}
        for sv in kept_segs:
            row[sv] = cell.get((gv, sv), 0.0)
        out_rows.append(row)
    seg_keys = list(kept_segs)

    dropped_segs = len(segments_all) - len(kept_segs)
    dropped_groups = len(groups) - len(kept_groups)
    title = html.escape(mapping.get("title") or (v_col + " of " + s_col + " per " + g_col + " (grouped bar)"))
    subtitle = html.escape(
        "Clusters of " + g_col + "; one bar per " + s_col + " (height = " + v_col + "), compared side by side. "
        + "Showing the comparable core: top " + str(len(kept_groups)) + " of " + str(len(groups)) + " "
        + g_col + " × top " + str(len(kept_segs)) + " of " + str(len(segments_all)) + " " + s_col
        + " by coverage; dropped " + str(dropped_groups) + " groups and " + str(dropped_segs)
        + " rarer segments (completeness per the paper).")
    width = max(900, len(kept_groups) * 70 + 80)
    height = 460

    return (
        HEAD.replace("__T__", title).replace("__SUB__", subtitle)
        + "const rows = " + json.dumps(out_rows) + ";\n"
        + "const segments = " + json.dumps(seg_keys) + ";\n"
        + "const segmentName = " + json.dumps(s_col) + ", valueName = " + json.dumps(v_col) + ";\n"
        + "const width = " + str(width) + ", height = " + str(height) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a weak-entity grouped bar chart to standalone HTML (D3 v7).")
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    rows = _rows_for(mapping, json.loads(Path(args.data).read_text(encoding="utf-8")))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(mapping, rows), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
