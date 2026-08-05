"""Reference word-cloud renderer for basic_entity (lexical key) selections (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_wordcloud.md. Each instance
is a word (lexical key) whose font size is area-proportional (scaleSqrt) to a scalar
attribute, laid out by the official d3-cloud plugin (loaded from a CDN). The layout is
asynchronous; words are drawn in its on("end") callback. Reads a flat row array or the
grouped Mondial database (mapping["table"]). HTML by plain concatenation. Std-lib only.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

JS_BODY = """
const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const g = svg.append("g").attr("transform", `translate(${width / 2},${height / 2})`);
const tip = d3.select("#tip");
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

const maxV = d3.max(data, d => d.value) || 1;
const minV = d3.min(data, d => d.value) || 0;
const fontScale = d3.scaleSqrt().domain([minV, maxV]).range([10, 64]);
// Colour: paper Section-3 rule — scalar -> spectrum, discrete -> ordinal key; else per-word default.
const colorScalar = colorName && colorType === "scalar";
const colorSeq = colorScalar ? d3.scaleSequential(d3.interpolateViridis).domain(d3.extent(data, d => +d.color)) : null;
const colorOrd = colorName ? d3.scaleOrdinal(Array.from(new Set(data.map(d => d.color))), d3.schemeCategory10) : d3.scaleOrdinal(d3.schemeCategory10);
const wordFill = (d, i) => colorName ? (colorScalar ? colorSeq(+d.color) : colorOrd(d.color)) : colorOrd(i % 10);

const words = data.map(d => ({ text: d.text, value: d.value, color: d.color, size: fontScale(d.value) }));

d3.layout.cloud()
  .size([width, height])
  .words(words)
  .padding(2)
  .rotate(0)
  .font("Arial")
  .fontSize(d => d.size)
  .on("end", draw)
  .start();

function draw(laid) {
  const text = g.selectAll("text").data(laid).join("text")
    .attr("font-family", "Arial")
    .attr("font-size", d => d.size + "px")
    .attr("fill", (d, i) => wordFill(d, i))
    .attr("text-anchor", "middle")
    .attr("transform", d => `translate(${d.x},${d.y}) rotate(${d.rotate})`)
    .text(d => d.text);

  text
    .on("mouseover", (event, d) => {
      text.attr("fill-opacity", w => w === d ? 1 : 0.2);
      tip.style("opacity", 1).html("<strong>" + d.text + "</strong><br>" + valueName + ": " + d.value);
      moveTip(event);
    })
    .on("mousemove", moveTip)
    .on("mouseout", () => { text.attr("fill-opacity", 1); tip.style("opacity", 0); });
}
"""

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__T__</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/d3-cloud@1/build/d3.layout.cloud.js"></script>
<style>
  body { font-family: Arial, sans-serif; margin: 16px; }
  h1 { font-size: 18px; margin-bottom: 2px; }
  #sub { color: #555; font-size: 12px; margin: 0 0 8px; }
  #tip { position: absolute; opacity: 0; pointer-events: none; background: rgba(0,0,0,0.82);
         color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px; line-height: 1.4; }
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
    text_col, size_col = mapping["text"], mapping["size"]
    color_col = mapping.get("color")  # paper: optional a2 colour of the words

    words: list[dict[str, Any]] = []
    for r in rows:
        try:
            v = float(r[size_col])
        except (TypeError, ValueError, KeyError):
            continue
        if v < 0:
            continue
        w = {"text": html.escape(str(r.get(text_col))), "value": v}
        if color_col is not None:
            w["color"] = html.escape(str(r.get(color_col)))
        words.append(w)

    title = html.escape(mapping.get("title") or (text_col + " sized by " + size_col + " (word cloud)"))
    subtitle = html.escape("Each " + text_col + " is a word; font size (area) ∝ " + size_col
                           + ". " + str(len(words)) + " words; ones that do not fit are dropped by the layout.")
    width, height = 960, 620

    return (
        HEAD.replace("__T__", title).replace("__SUB__", subtitle)
        + "const data = " + json.dumps(words) + ";\n"
        + "const valueName = " + json.dumps(size_col) + ";\n"
        + "const colorName = " + json.dumps(color_col) + ", colorType = " + json.dumps(mapping.get("color_type")) + ";\n"
        + "const width = " + str(width) + ", height = " + str(height) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a basic-entity word cloud to standalone HTML (D3 v7).")
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
