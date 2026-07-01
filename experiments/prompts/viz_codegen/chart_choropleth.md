# Chart-specific instructions: Choropleth map (basic_entity)

## Pattern context

This renderer serves the `basic_entity` pattern when the entity key is a **geographical region**: instances of one entity `E` are identified by a region key `k`, and a scalar attribute `a1` colours each region. The visualisation is a **choropleth map**.

## Mapping fields

The mapping names a table and the columns, by **role** — fill them from the actual selection; the
values below are placeholders, not fixed names. This renderer must work for **any** basic-entity
selection whose key is a geographical region, not one specific table:

```json
{ "table": "<entity table>", "region": "<geographical key column>", "color": "<scalar attribute>" }
```

Never hard-code these names; always read them from the mapping at run time.

- `region` (`k`) — the geographical key. It must be **matchable to the basemap** (e.g. a country name that matches the map's `properties.name`); a dataset-specific non-standard code will not match and those regions will be left blank.
- `color` (`a1`) — the scalar attribute that sets each region's colour (numeric).
- Optional `title`.

## External dependency (geography)

A choropleth needs region geometry that is **not** in the relational rows. Load it from an official CDN inside the produced HTML (in addition to D3 v7):

```html
<script src="https://cdn.jsdelivr.net/npm/topojson-client@3"></script>
```

and fetch a world basemap, e.g. `https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json`, converting it with `topojson.feature(world, world.objects.countries).features`.

## Required data transformation

Build a lookup `region (lower-cased) -> color value` from the rows (drop non-numeric `color`). Inject that lookup. At draw time, for each map feature, look up its name in the lookup; colour it by value, or leave it neutral grey if there is no matching row.

## D3 v7 construction

- A projection (e.g. `d3.geoNaturalEarth1()` fitted to the size) and `d3.geoPath()`.
- One `<path>` per country feature; fill by `d3.scaleSequential(d3.interpolateYlGnBu).domain([0, maxValue])` when the feature has a value, else `#eee`.
- A short colour legend is welcome.

## Interaction (per the base contract)

Hover a region with a value → tooltip showing the region and the value, and emphasise it (e.g. a contrasting stroke) while leaving the rest; restore on mouse-out.

## Pitfalls to respect

- The `region` key must join to the basemap names; if the dataset uses non-standard codes, prefer the entity's name column. Unmatched regions are drawn grey, not dropped.
- The geometry is fetched at run time from the CDN; the relational data is still injected inline.
- Use only D3 v7 APIs (plus `topojson-client`) — no `d3.nest` / `d3.event` removed in v6+.
