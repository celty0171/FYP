from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

OTHER_KEY = "(other)"

JS_BODY = """
const margin = {top: 24, right: 20, bottom: 20, left: 160};
const innerW = width - margin.left - margin.right;
const innerH = height - margin.top - margin.bottom;

const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

const series = d3.stack().keys(segments)(rows);
const y = d3.scaleBand().domain(rows.map(d => d.__group)).range([0, innerH]).padding(0.15);
const maxTotal = d3.max(rows, d => segments.reduce((s, k) => s + (d[k] || 0), 0)) || 1;
const x = d3.scaleLinear().domain([0, maxTotal]).range([0, innerW]).nice();
const palette = d3.quantize(d3.interpolateRainbow, Math.max(2, segments.length));
const color = d3.scaleOrdinal()
  .domain(segments)
  .range(segments.map((s, i) => s === otherKey ? "#cccccc" : palette[i % palette.length]));

g.append("g").call(d3.axisTop(x).ticks(6));
g.append("g").call(d3.axisLeft(y)).selectAll("text").style("font-size", "8px");

const tip = d3.select("#tip");
// Escape values only where they enter innerHTML (the tooltip); on-canvas labels use .text() and stay raw.
const escHtml = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

const layer = g.append("g").selectAll("g").data(series).join("g").attr("fill", d => color(d.key));
const rect = layer.selectAll("rect").data(d => d.map(v => (v.key = d.key, v))).join("rect")
  .attr("y", d => y(d.data.__group))
  .attr("x", d => x(d[0]))
  .attr("width", d => Math.max(0, x(d[1]) - x(d[0])))
  .attr("height", y.bandwidth())
  .attr("fill-opacity", 0.9);

rect
  .on("mouseover", (event, d) => {
    rect.attr("fill-opacity", r => r.key === d.key ? 0.95 : 0.2);
    tip.style("opacity", 1).html("<strong>" + escHtml(d.data.__group) + "</strong><br>" + segmentName + ": " + escHtml(d.key) + "<br>" + valueName + ": " + (d.data[d.key] || 0));
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
    # How many shared segments to keep before folding the tail into "(other)".
    max_segments = int(mapping.get("max_segments", 12))

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

    # Completeness: keep the segments shared across the most groups (the comparable core),
    # ranked by coverage then total value; fold the remaining long tail into one "(other)" band.
    ranked = sorted(segments_all, key=lambda s: (len(seg_groups[s]), seg_total[s]), reverse=True)
    kept = ranked[:max_segments]
    kept_set = set(kept)
    folded = [s for s in segments_all if s not in kept_set]
    has_other = bool(folded)

    seg_keys = list(kept)
    if has_other:
        seg_keys.append(OTHER_KEY)

    # One row object per group: every kept segment present (missing = 0), plus the folded "(other)".
    out_rows = []
    for gv in groups:
        row: dict[str, Any] = {"__group": gv}
        for sv in kept:
            row[sv] = cell.get((gv, sv), 0.0)
        if has_other:
            row[OTHER_KEY] = sum(cell.get((gv, sv), 0.0) for sv in folded)
        out_rows.append(row)

    title = html.escape(mapping.get("title") or (v_col + " of " + s_col + " per " + g_col + " (stacked bar)"))
    cov_note = ("kept the " + str(len(kept)) + " most widely shared " + s_col + " values; folded "
                + str(len(folded)) + " rarer ones into " + OTHER_KEY) if has_other else \
               ("all " + str(len(kept)) + " " + s_col + " values shared across bars")
    subtitle = html.escape("One bar per " + g_col + ", stacked by " + s_col + "; length = " + v_col
                           + ". " + str(len(groups)) + " bars; " + cov_note + " (completeness per the paper).")
    width = 1000
    height = max(360, len(groups) * 13 + 60)

    return (
        HEAD.replace("__T__", title).replace("__SUB__", subtitle)
        + "const rows = " + json.dumps(out_rows) + ";\n"
        + "const segments = " + json.dumps(seg_keys) + ";\n"
        + "const otherKey = " + json.dumps(OTHER_KEY) + ";\n"
        + "const segmentName = " + json.dumps(s_col) + ", valueName = " + json.dumps(v_col) + ";\n"
        + "const width = " + str(width) + ", height = " + str(height) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a weak-entity stacked bar chart to standalone HTML (D3 v7).")
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
