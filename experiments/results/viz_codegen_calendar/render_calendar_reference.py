"""Reference calendar renderer for basic_entity selections (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_calendar.md. Reads a
chart mapping and the entity rows at run time (a flat array, or the grouped Mondial
database selected by mapping["table"]) and emits a complete, standalone D3 v7
calendar HTML file: one year strip per year that has data, day cells coloured by the
day's value (count of instances, or sum of an optional measure). HTML assembled by
plain concatenation (no f-string / str.format). Std-lib only.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")

JS_BODY = """
const cell = 15;
const yearH = cell * 7 + 22;
const leftPad = 46;

const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const g = svg.append("g").attr("transform", "translate(10,10)");

const maxV = d3.max(Object.values(dayValue)) || 1;
const color = d3.scaleSequential(d3.interpolateBlues).domain([0, maxV]);
const fmtDay = d3.utcFormat("%Y-%m-%d");
const weekIdx = d => d3.utcSunday.count(d3.utcYear(d), d);

const tip = d3.select("#tip");
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

// Month guides across the top, aligned to the shared week columns.
const ref = years[0];
const months = d3.utcMonths(new Date(Date.UTC(ref, 0, 1)), new Date(Date.UTC(ref + 1, 0, 1)));
g.append("g").attr("transform", "translate(" + leftPad + ",0)").selectAll("text").data(months).join("text")
  .attr("x", m => weekIdx(m) * cell).attr("y", 9).attr("font-size", "9px").attr("fill", "#666")
  .text(m => d3.utcFormat("%b")(m));

years.forEach((yr, i) => {
  const gy = g.append("g").attr("transform", "translate(" + leftPad + "," + (i * yearH + 16) + ")");
  gy.append("text").attr("x", -8).attr("y", cell * 3.5).attr("text-anchor", "end")
    .attr("font-weight", "bold").attr("font-size", "11px").text(yr);
  const days = d3.utcDays(new Date(Date.UTC(yr, 0, 1)), new Date(Date.UTC(yr + 1, 0, 1)));
  gy.selectAll("rect").data(days).join("rect")
    .attr("width", cell - 1).attr("height", cell - 1)
    .attr("x", d => weekIdx(d) * cell).attr("y", d => d.getUTCDay() * cell)
    .attr("fill", d => { const v = dayValue[fmtDay(d)]; return v ? color(v) : "#eee"; })
    .attr("stroke", "#fff")
    .on("mouseover", (event, d) => {
      const iso = fmtDay(d);
      const v = dayValue[iso];
      if (!v) return;
      d3.select(event.currentTarget).attr("stroke", "#222");
      tip.style("opacity", 1).html("<strong>" + iso + "</strong><br>" + valueName + ": " + v + "<br>" + (dayItems[iso] || ""));
      moveTip(event);
    })
    .on("mousemove", moveTip)
    .on("mouseout", (event) => { d3.select(event.currentTarget).attr("stroke", "#fff"); tip.style("opacity", 0); });
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
  #tip { position: absolute; opacity: 0; pointer-events: none; background: rgba(0,0,0,0.82);
         color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px; line-height: 1.4; max-width: 280px; }
</style>
</head>
<body>
<h1>__T__</h1>
<p id="sub">__SUB__</p>
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
    date_col = mapping["date"]
    key_col = mapping.get("key")
    measure_col = mapping.get("measure")

    day_value: dict[str, float] = {}
    day_items: dict[str, list[str]] = {}
    for r in rows:
        ds = r.get(date_col)
        if not ds:
            continue
        m = DATE_RE.match(str(ds))
        if not m:
            continue
        iso = m.group(0)
        if measure_col is not None:
            try:
                v = float(r[measure_col])
            except (TypeError, ValueError, KeyError):
                continue
        else:
            v = 1.0
        day_value[iso] = day_value.get(iso, 0.0) + v
        day_items.setdefault(iso, []).append(html.escape(str(r.get(key_col))) if key_col else iso)

    years = sorted({int(iso[:4]) for iso in day_value})
    # Cap the tooltip instance list per day.
    items_str = {iso: (", ".join(v[:8]) + (" …" if len(v) > 8 else "")) for iso, v in day_items.items()}

    value_name = "count" if measure_col is None else str(measure_col)
    title = html.escape(mapping.get("title") or ("Calendar of " + date_col))
    subtitle = html.escape("Each instance placed by " + date_col + "; day colour = " + value_name
                           + ". " + str(sum(len(v) for v in day_items.values())) + " instances across "
                           + str(len(years)) + " years (" + (str(years[0]) + "–" + str(years[-1]) if years else "—") + ").")
    width = 46 + 53 * 15 + 30
    height = max(200, len(years) * (15 * 7 + 22) + 40)

    return (
        HEAD.replace("__T__", title).replace("__SUB__", subtitle)
        + "const dayValue = " + json.dumps(day_value) + ";\n"
        + "const dayItems = " + json.dumps(items_str) + ";\n"
        + "const years = " + json.dumps(years) + ";\n"
        + "const valueName = " + json.dumps(value_name) + ";\n"
        + "const width = " + str(width) + ", height = " + str(height) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a basic-entity calendar chart to standalone HTML (D3 v7).")
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    rows = _rows_for(mapping, json.loads(Path(args.data).read_text(encoding="utf-8")))
    html_doc = render(mapping, rows)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {out} ({len(html_doc)} bytes)")


if __name__ == "__main__":
    main()
