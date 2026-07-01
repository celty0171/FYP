# viz_codegen_bar — Step 3 deterministic renderer (basic_entity → bar chart, D3 v7)

Fifth Step-3 cell and the first of the `basic_entity` row. Layered prompt
(`prompts/viz_codegen/base_d3v7.md` + `chart_bar.md`). Same paradigm: the model writes
`render(mapping, rows) -> HTML` once; data is read at run time and never enters the prompt.

## Case and inputs

- Pattern `basic_entity`, case 1 (`country`): instances identified by a key, described by scalar
  attributes. Stage-1/2 recommends bar chart / choropleth / word cloud
  (`prompt_v8_thinking/responses/case_1.json`, `{x: code, y: population}` for the bar).
- `mapping_country.json` — `{table: country, key: name, measure: population}` (`name` used as the
  key for readable labels).
- Data: full `mondial_database/mondial_data.json`; renderer selects `data["tables"]["country"]`.

## Renderer

`render_bar_reference.py` — D3 v7, std-lib only, HTML by plain concatenation (no f-string /
`str.format`). Construction:

- **One bar per entity instance** `{label: key, value: measure}`; drops non-numeric measures; sorts
  by measure **descending**. No aggregation.
- **Horizontal** bar chart (`d3.scaleBand` on keys, `d3.scaleLinear` on the measure, `.nice()`) so
  246 category labels stay readable; measure axis on top, value labels at bar ends when they fit;
  tall canvas (`len·14`).
- Hover a bar → tooltip (key, measure) and emphasise that bar while dimming the rest.

## Validation

| check | result |
|-------|--------|
| bars | 246 (one per country) |
| order | sorted descending; top 3 China 1.41B, India 1.21B, United States 331M |
| construction | D3 v7, `scaleBand` + `scaleLinear`, horizontal (`axisLeft` categories) |
| contract | no forbidden APIs, interaction (tooltip + dim others), subtitle, no f-string, complete HTML |

## Reproduce

```bash
cd experiments
python3 results/viz_codegen_bar/render_bar_reference.py \
  --mapping results/viz_codegen_bar/mapping_country.json \
  --data mondial_database/mondial_data.json \
  --out results/viz_codegen_bar/country_reference.html
```

## Status / next — the rest of the basic_entity row

Bar done. The `basic_entity` group has more charts, with these data/dependency notes:

- **scatter** (2 scalars `a1`, `a2`) and **bubble** (3 scalars + size) — share one cartesian
  data-prep recipe (case 3 `lake`: elevation / depth / dam_height); natural next pair.
- **calendar** — needs a date attribute (e.g. `organization.established`).
- **choropleth** — needs external **geography** (TopoJSON/GeoJSON country boundaries), so it breaks
  the "data is just relational rows" contract; treat as a special cell.
- **word cloud** — needs the **d3-cloud** plugin CDN; special cell.

Qwen/Coder run deferred until Coder-32B (port 8004) is available.
