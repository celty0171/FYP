"""Reference choropleth renderer for basic_entity (geographical key) selections (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_choropleth.md. Colours a
**world-atlas** basemap (50m sovereign country outlines) by a scalar attribute. Each sovereign
is a single polygon (the UK, Belgium each one shape) and dependencies are merged into their
sovereign; regions join on the ISO 3166-1 numeric id via ``mondial_iso_crosswalk.json`` (with a
lowercased-name fallback).

A highly skewed measure (population/area/gdp) is spread with a sqrt colour scale and a lifted
floor so small countries stay visible; borders are light grey so every shape is outlined. The
geometry is fetched at run time from a CDN (pinned); TopoJSON vs GeoJSON is auto-detected. Reads a
flat row array or the grouped Mondial database (mapping["table"]). HTML by plain concatenation
(no f-string / str.format). Std-lib only.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

# World-atlas basemap: 50m sovereign country outlines, joined on the ISO 3166-1 numeric id
# exposed as each feature's d.id.
BASEMAP_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json"
BASEMAP_LABEL = "World-atlas countries (sovereign outlines)"

JS_BODY = """
const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const g = svg.append("g");
const tip = d3.select("#tip");
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

// Each feature's join key (ISO numeric d.id) and its display name.
const keyOf = (d) => String(d.id);
const nameOf = (d) => { const p = d.properties || {}; return p.name || p.NAME || ""; };
const lookup = (d) => {
  let v = valueByKey[keyOf(d)];
  if (v === undefined) v = valueByKey[nameOf(d).toLowerCase()];
  return v;
};

const vals = Object.values(valueByKey);
const vmax = d3.max(vals) || 1;
// Measures like population / area / gdp are highly skewed, so a linear ramp leaves almost every
// country at the palette's lightest end (invisible on a white map). Spread the domain with a sqrt
// scale and lift the floor so even the smallest value gets a clearly visible tint.
const tScale = d3.scaleSqrt().domain([0, vmax]).range([0, 1]).clamp(true);
const color = v => d3.interpolateYlGnBu(0.15 + 0.85 * tScale(v));

d3.json(basemapUrl).then(geo => {
  const countries = (geo.type === "Topology")
    ? topojson.feature(geo, geo.objects.countries).features
    : geo.features;
  const projection = d3.geoNaturalEarth1().fitSize([width, height], {type: "FeatureCollection", features: countries});
  const path = d3.geoPath(projection);

  g.selectAll("path").data(countries).join("path")
    .attr("d", path)
    .attr("stroke", "#9aa4b2").attr("stroke-width", 0.4)
    .attr("fill", d => {
      const v = lookup(d);
      return (v === undefined) ? "#e6e8ec" : color(v);
    })
    .on("mouseover", (event, d) => {
      const v = lookup(d);
      if (v === undefined) return;
      d3.select(event.currentTarget).attr("stroke", "#222").attr("stroke-width", 1.2).raise();
      tip.style("opacity", 1).html("<strong>" + nameOf(d) + "</strong><br>" + valueName + ": " + v);
      moveTip(event);
    })
    .on("mousemove", moveTip)
    .on("mouseout", (event) => { d3.select(event.currentTarget).attr("stroke", "#9aa4b2").attr("stroke-width", 0.4); tip.style("opacity", 0); });

  // simple legend
  const lw = 180, lh = 8, lx = 20, ly = height - 30;
  const lg = svg.append("g").attr("transform", `translate(${lx},${ly})`);
  const stops = d3.range(0, 1.001, 0.1);
  lg.selectAll("rect").data(stops.slice(0, -1)).join("rect")
    .attr("x", (d, i) => i * lw / (stops.length - 1)).attr("width", lw / (stops.length - 1)).attr("height", lh)
    .attr("fill", d => color(d * vmax));
  lg.append("text").attr("y", -4).attr("font-size", "10px").text(valueName + " (0 – " + Math.round(vmax) + ")");
});
"""

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__T__</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/topojson-client@3"></script>
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


def _load_json_sibling(name: str) -> dict[str, Any]:
    try:
        return json.loads((Path(__file__).with_name(name)).read_text("utf-8"))
    except Exception:
        return {}


_ISO = _load_json_sibling("mondial_iso_crosswalk.json")      # code -> ISO id, name -> ISO id
ISO_CODE_TO_ID = _ISO.get("code_to_id", {})
ISO_NAME_TO_ID = _ISO.get("name_to_id", {})


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


def _value_by_key(rows: list[dict[str, Any]], region_col: str, color_col: str) -> dict[str, float]:
    """Key each value by its ISO 3166-1 numeric id (the world-atlas feature id), plus a
    lowercased-name fallback that matches the feature name directly."""
    out: dict[str, float] = {}
    for r in rows:
        try:
            v = float(r[color_col])
        except (TypeError, ValueError, KeyError):
            continue
        rv = r.get(region_col)
        if rv is None:
            continue
        iso = ISO_CODE_TO_ID.get(rv) or ISO_NAME_TO_ID.get(rv)
        if iso:
            out[str(iso)] = v
        out[str(rv).strip().lower()] = v            # name fallback (matches feature name)
    return out


def render(mapping: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    region_col, color_col = mapping["region"], mapping["color"]

    value_by_key = _value_by_key(rows, region_col, color_col)

    title = html.escape(mapping.get("title") or (color_col + " by " + region_col + " (choropleth)"))
    subtitle = html.escape("Regions coloured by " + color_col + " · basemap: " + BASEMAP_LABEL
                           + ". " + str(len([k for k in value_by_key])) + " keys mapped.")
    width, height = 980, 560

    return (
        HEAD.replace("__T__", title).replace("__SUB__", subtitle)
        + "const valueByKey = " + json.dumps(value_by_key) + ";\n"
        + "const valueName = " + json.dumps(color_col) + ";\n"
        + "const basemapUrl = " + json.dumps(BASEMAP_URL) + ";\n"
        + "const width = " + str(width) + ", height = " + str(height) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a basic-entity choropleth map to standalone HTML (D3 v7).")
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
