"""Reference choropleth renderer for basic_entity (geographical key) selections (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_choropleth.md. Colours a
world basemap by a scalar attribute. It joins each region to the basemap by its stable
ISO 3166-1 **numeric id** (``d.id``, e.g. 840 = USA) via ``mondial_iso_crosswalk.json``,
which resolves both the Mondial ``code`` and ``name`` to that id — so wording differences
(United States vs United States of America, Czechia, Dem. Rep. Congo, accents, "Is."/"Rep."
abbreviations) no longer grey out a country. A lowercased-name lookup is kept as a fallback,
so anything outside the crosswalk still behaves as before and the renderer degrades
gracefully if the crosswalk file is missing. The relational data is injected inline; the
geometry is fetched at run time from a CDN (world-atlas). Reads a flat row array or the
grouped Mondial database (mapping["table"]). HTML by plain concatenation (no f-string /
str.format). Std-lib only.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

JS_BODY = """
const svg = d3.select("#chart").append("svg").attr("width", width).attr("height", height);
const g = svg.append("g");
const tip = d3.select("#tip");
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

// Join on the basemap's stable ISO numeric id first (wording-independent); fall back to the
// feature name for anything not covered by the crosswalk.
const lookup = (d) => {
  let v = valueByRegion[String(d.id)];
  if (v === undefined) v = valueByRegion[(d.properties.name || "").toLowerCase()];
  return v;
};

const vals = Object.values(valueByRegion);
const color = d3.scaleSequential(d3.interpolateYlGnBu).domain([0, d3.max(vals) || 1]);

d3.json("https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json").then(world => {
  const countries = topojson.feature(world, world.objects.countries).features;
  const projection = d3.geoNaturalEarth1().fitSize([width, height], {type: "FeatureCollection", features: countries});
  const path = d3.geoPath(projection);

  g.selectAll("path").data(countries).join("path")
    .attr("d", path)
    .attr("stroke", "#fff").attr("stroke-width", 0.4)
    .attr("fill", d => {
      const v = lookup(d);
      return (v === undefined) ? "#eee" : color(v);
    })
    .on("mouseover", (event, d) => {
      const v = lookup(d);
      if (v === undefined) return;
      d3.select(event.currentTarget).attr("stroke", "#222").attr("stroke-width", 1.2).raise();
      tip.style("opacity", 1).html("<strong>" + d.properties.name + "</strong><br>" + valueName + ": " + v);
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


def _load_crosswalk() -> tuple[dict[str, str], dict[str, str]]:
    """Mondial code/name -> ISO numeric id, from the sibling JSON (empty on any failure)."""
    try:
        d = json.loads((Path(__file__).with_name("mondial_iso_crosswalk.json")).read_text("utf-8"))
        return d.get("code_to_id", {}), d.get("name_to_id", {})
    except Exception:
        return {}, {}


CODE_TO_ID, NAME_TO_ID = _load_crosswalk()


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

    # Key each value by the basemap's ISO numeric id (via the crosswalk, wording-independent)
    # AND by the lowercased region string (fallback for anything the crosswalk doesn't cover).
    value_by_region: dict[str, float] = {}
    matched_ids = 0
    for r in rows:
        try:
            v = float(r[color_col])
        except (TypeError, ValueError, KeyError):
            continue
        rv = r.get(region_col)
        iso = CODE_TO_ID.get(rv) or NAME_TO_ID.get(rv)
        if iso:
            value_by_region[iso] = v
            matched_ids += 1
        if rv is not None:
            value_by_region[str(rv).strip().lower()] = v

    title = html.escape(mapping.get("title") or (color_col + " by " + region_col + " (choropleth)"))
    subtitle = html.escape("Regions coloured by " + color_col + "; joined on ISO id to the world "
                           + "basemap (" + str(matched_ids) + " matched via crosswalk, name fallback otherwise).")
    width, height = 980, 560

    return (
        HEAD.replace("__T__", title).replace("__SUB__", subtitle)
        + "const valueByRegion = " + json.dumps(value_by_region) + ";\n"
        + "const valueName = " + json.dumps(color_col) + ";\n"
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
