# viz_codegen_choropleth — Step 3 deterministic renderer (basic_entity → choropleth, D3 v7)

The geographical chart of the `basic_entity` row. Layered prompt (`base_d3v7.md` +
`chart_choropleth.md`). The first **special** cell: it needs external map geometry, which is fetched
from a CDN at run time — the relational data is still injected inline.

## Inputs

- `mapping_country.json` — `{table: country, region: name, color: population}`. **`region` is the
  country `name`**, not the Mondial `code`: Mondial codes (AL, GR, D…) are licence-plate style, not
  ISO, so they do not join the basemap; the country name does.
- Data: `mondial_database/mondial_data.json` → `data["tables"]["country"]` (246 regions with a
  numeric population).

## Renderer

`render_choropleth_reference.py` — D3 v7 + `topojson-client@3` + `world-atlas@2` (CDN), std-lib only,
HTML by plain concatenation. Builds a `region(lower) -> color value` lookup from the rows; at draw
time loads `countries-110m`, projects with `d3.geoNaturalEarth1()` + `d3.geoPath()`, and fills each
feature by `d3.scaleSequential(d3.interpolateYlGnBu)` on its looked-up value, or `#eee` if no row
matches. Legend; hover a region → tooltip (region, value) + contrasting stroke.

## Validation (structural — pixels need a browser with CDN access)

246 regions in the lookup; `topojson-client` + `world-atlas` loaded; `geoNaturalEarth1` + `geoPath`;
name-join with grey fallback for unmatched; sequential colour; interaction; complete HTML; no
forbidden APIs; no f-string.

## Known limitation — the join key

The renderer joins `region` values to the basemap feature names (lower-cased). Step 2 maps `region`
to the entity **key** (`code` for `country`), which does **not** match map names — feeding that
mapping renders a mostly-grey map. A good choropleth therefore needs the region key to be a
basemap-matchable name; this is the geographical-character gap Step 2 already flags as *conditional*
(it cannot prove a column is geographical from its SQL type). Demonstrated: `region=name` colours
246 countries; `region=code` renders but mostly grey.

## Reproduce

```bash
cd experiments
python3 results/viz_codegen_choropleth/render_choropleth_reference.py \
  --mapping results/viz_codegen_choropleth/mapping_country.json \
  --data mondial_database/mondial_data.json \
  --out results/viz_codegen_choropleth/country_reference.html
```
