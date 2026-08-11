"""Reference choropleth renderer for basic_entity (geographical key) selections (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_choropleth.md. Colours a world
basemap by a scalar attribute. It uses the Natural Earth **admin-0 map units** basemap (50m),
so dependencies an ordinary country outline folds into a sovereign state — French overseas
departments, Macao, Svalbard, the West Bank / Gaza split, and many island territories — are
separate, joinable polygons. Each map unit is resolved to its Mondial country via
``mondial_mapunit_crosswalk.json`` (``GU_A3`` -> Mondial code, built per unit by own name else
sovereign), so wording differences no longer grey out a country AND every sub-unit of a state
that map units *split* — England/Scotland/Wales/N.Ireland, the Belgian regions — shares its
country's value instead of only one unit colouring. Coverage is 242/246 Mondial countries. A
lowercased-name lookup is kept as a fallback, so the renderer degrades gracefully if the
crosswalk file is missing.

The relational data is injected inline; the geometry is fetched at run time from a CDN (pinned
Natural Earth release). Reads a flat row array or the grouped Mondial database (mapping["table"]).
HTML by plain concatenation (no f-string / str.format). Std-lib only.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

BASEMAP_URL = ("https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@v5.1.2/"
               "geojson/ne_50m_admin_0_map_units.geojson")

JS_BODY = """
const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const g = svg.append("g");
const tip = d3.select("#tip");
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

// Resolve each map unit to its Mondial country via GU_A3 -> code, then to the value; every
// sub-unit of a split state (England/Scotland/Wales/N.Ireland, the Belgian regions) shares its
// country's value. Fall back to the feature name for anything not covered by the crosswalk.
const lookup = (p) => {
  const code = guToCode[p.GU_A3];
  let v = (code !== undefined) ? valueByCode[code] : undefined;
  if (v === undefined) v = valueByCode[(p.NAME || "").toLowerCase()];
  return v;
};

const vals = Object.values(valueByCode);
const color = d3.scaleSequential(d3.interpolateYlGnBu).domain([0, d3.max(vals) || 1]);

d3.json(basemapUrl).then(geo => {
  const countries = geo.features;
  const projection = d3.geoNaturalEarth1().fitSize([width, height], {type: "FeatureCollection", features: countries});
  const path = d3.geoPath(projection);

  g.selectAll("path").data(countries).join("path")
    .attr("d", path)
    .attr("stroke", "#fff").attr("stroke-width", 0.4)
    .attr("fill", d => {
      const v = lookup(d.properties || {});
      return (v === undefined) ? "#eee" : color(v);
    })
    .on("mouseover", (event, d) => {
      const p = d.properties || {};
      const v = lookup(p);
      if (v === undefined) return;
      d3.select(event.currentTarget).attr("stroke", "#222").attr("stroke-width", 1.2).raise();
      tip.style("opacity", 1).html("<strong>" + (p.NAME || "") + "</strong><br>" + valueName + ": " + v);
      moveTip(event);
    })
    .on("mousemove", moveTip)
    .on("mouseout", (event) => { d3.select(event.currentTarget).attr("stroke", "#fff").attr("stroke-width", 0.4); tip.style("opacity", 0); });

  // simple legend
  const lw = 180, lh = 8, lx = 20, ly = height - 30;
  const lg = svg.append("g").attr("transform", `translate(${lx},${ly})`);
  const dmax = d3.max(vals) || 1;
  const stops = d3.range(0, 1.001, 0.1);
  lg.selectAll("rect").data(stops.slice(0, -1)).join("rect")
    .attr("x", (d, i) => i * lw / (stops.length - 1)).attr("width", lw / (stops.length - 1)).attr("height", lh)
    .attr("fill", d => color(d * dmax));
  lg.append("text").attr("y", -4).attr("font-size", "10px").text(valueName + " (0 – " + Math.round(dmax) + ")");
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


def _load_crosswalk() -> tuple[dict[str, str], dict[str, str], str]:
    """GU_A3 -> Mondial code and Mondial name -> code, plus the basemap URL, from the sibling
    JSON (empty/defaults on failure)."""
    try:
        d = json.loads((Path(__file__).with_name("mondial_mapunit_crosswalk.json")).read_text("utf-8"))
        return d.get("gu_to_code", {}), d.get("name_to_code", {}), d.get("basemap", BASEMAP_URL)
    except Exception:
        return {}, {}, BASEMAP_URL


GU_TO_CODE, NAME_TO_CODE, CROSSWALK_BASEMAP = _load_crosswalk()


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
    region_col, color_col = mapping["region"], mapping["color"]

    # Key each value by the Mondial country *code* (resolving a name-valued region via
    # name_to_code), plus the lowercased region string as a fallback. The JS then maps each map
    # unit's GU_A3 -> code -> value, so all sub-units of a split state share the value.
    value_by_code: dict[str, float] = {}
    matched = 0
    for r in rows:
        try:
            v = float(r[color_col])
        except (TypeError, ValueError, KeyError):
            continue
        rv = r.get(region_col)
        if rv is None:
            continue
        code = NAME_TO_CODE.get(rv, rv)      # a name -> its code; else assume rv is already a code
        value_by_code[str(code)] = v
        value_by_code[str(rv).strip().lower()] = v
        matched += 1

    title = html.escape(mapping.get("title") or (color_col + " by " + region_col + " (choropleth)"))
    subtitle = html.escape("Regions coloured by " + color_col + "; each Natural Earth map unit is "
                           + "resolved (GU_A3 -> Mondial country) so every sub-unit of a split "
                           + "state is filled. " + str(matched) + " rows mapped.")
    width, height = 980, 560

    return (
        HEAD.replace("__T__", title).replace("__SUB__", subtitle)
        + "const valueByCode = " + json.dumps(value_by_code) + ";\n"
        + "const guToCode = " + json.dumps(GU_TO_CODE) + ";\n"
        + "const valueName = " + json.dumps(color_col) + ";\n"
        + "const basemapUrl = " + json.dumps(CROSSWALK_BASEMAP) + ";\n"
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
