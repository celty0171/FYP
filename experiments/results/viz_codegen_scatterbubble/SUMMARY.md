# viz_codegen_scatterbubble — Step 3 deterministic renderers (basic_entity → scatter + bubble, D3 v7)

Sixth and seventh Step-3 cells, the cartesian pair of the `basic_entity` row. Two layered prompt
blocks (`chart_scatter.md`, `chart_bubble.md`) on the shared `base_d3v7.md`; **one** reference
renderer serves both, because bubble is a scatter with a third scalar encoded as area — they share
one cartesian data-prep recipe. Same paradigm: the renderer is written once; data is read at run
time and never enters the prompt.

## Case and inputs

- Pattern `basic_entity`, case 3 (`lake`): scalar attributes `elevation`, `depth`, `dam_height`,
  `area`. Stage-1/2 lists bar / scatter / bubble (`prompt_v8_thinking/responses/case_3.json`:
  scatter `{x: elevation, y: depth}`, bubble `{x: elevation, y: depth, size: dam_height}`).
- `mapping_lake_scatter.json` — `{table: lake, key: name, x: elevation, y: depth}`.
- `mapping_lake_bubble.json` — `{… , size: dam_height}`.
- Data: full `mondial_database/mondial_data.json` → `data["tables"]["lake"]`.

## Renderer

`render_scatterbubble_reference.py` — D3 v7, std-lib only, HTML by plain concatenation. One renderer,
two charts:

- **Scatter** when the mapping has no `size`: one point per instance `{label, x, y}`, drop rows whose
  `x`/`y` are non-numeric, fixed radius.
- **Bubble** when the mapping has `size`: also reads `size` (drop rows missing it), radius via
  `d3.scaleSqrt` so **area** ∝ `size`; larger bubbles drawn first so small ones stay visible.
- Both: `d3.scaleLinear` axes with `.nice()` and axis titles; optional `color` → ordinal scale;
  partial fill-opacity; hover a point → tooltip (key + mapped values) and emphasise it while dimming
  the rest.

The scatter/bubble split is driven entirely by the injected `sizeName` (a column name or `null`) —
the same code path produces both, demonstrating the shared cartesian prep.

## Validation

| chart | points | size | radius scale |
|-------|--------|------|--------------|
| scatter (lake elevation × depth) | 195 (expected 195) | none | fixed (sizeName = null) |
| bubble (+ dam_height) | 22 (expected 22) | present | `d3.scaleSqrt` (area ∝ size) |

Both: D3 v7, `scaleLinear` axes + titles, hover interaction, no forbidden APIs, no f-string, complete
HTML.

## Reproduce

```bash
cd experiments
python3 results/viz_codegen_scatterbubble/render_scatterbubble_reference.py \
  --mapping results/viz_codegen_scatterbubble/mapping_lake_scatter.json \
  --data mondial_database/mondial_data.json \
  --out results/viz_codegen_scatterbubble/lake_scatter_reference.html
python3 results/viz_codegen_scatterbubble/render_scatterbubble_reference.py \
  --mapping results/viz_codegen_scatterbubble/mapping_lake_bubble.json \
  --data mondial_database/mondial_data.json \
  --out results/viz_codegen_scatterbubble/lake_bubble_reference.html
```

## Status / next — remaining basic_entity charts

- **calendar** — needs a date attribute (e.g. `organization.established`).
- **choropleth** — needs external TopoJSON/GeoJSON geography; breaks the relational-rows contract
  (special cell).
- **word cloud** — needs the d3-cloud plugin CDN (special cell).

Then the `weak` row: line / stacked bar / spider. Qwen/Coder runs deferred until Coder-32B (8004).
