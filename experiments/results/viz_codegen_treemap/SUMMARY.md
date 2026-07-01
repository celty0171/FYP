# viz_codegen_treemap — Step 3 deterministic renderer (one_many → tree map, D3 v7)

Third Step-3 cell (after chord and the D3 Sankey), on the layered prompt
(`prompts/viz_codegen/base_d3v7.md` + `chart_treemap.md`). Same paradigm: the model writes
`render(mapping, rows) -> HTML` once; data is read at run time and never enters the prompt.

## Case and inputs

- Pattern `one_many_relationship`, case 7 (`airport`): the child table `airport` carries a non-PK
  foreign key `island` to the parent entity `Ep = island`. Stage-1/2 selected **tree map**
  (`prompt_v8_thinking/responses/case_7.json`): `Ep = island`, `Ec = airport`, `kc = iata_code`,
  `a1 = elevation`.
- `mapping_airport.json` — `{table: airport, parent: island, child: iata_code, measure: elevation}`.
- Data: full `mondial_database/mondial_data.json`; renderer selects `data["tables"]["airport"]`
  (1304 rows).

## Renderer

`render_treemap_reference.py` — D3 v7 (`d3.hierarchy` + `d3.treemap`, both in the core bundle, no
plugin), std-lib only, HTML by plain concatenation (no f-string / `str.format`). Construction:

- Builds a **two-level hierarchy** root → island → airport; leaf value = `elevation` (floored at 0).
- **Excludes child rows with a null parent** — the 1019 airports with `island = null` are not part
  of the one_many selection and are dropped; 285 on-island airports across 171 islands remain.
- `d3.treemap().paddingInner(1).paddingTop(14)`; leaves coloured **by parent** so each island's
  airports share a hue; parent-group labels; child labels only when the cell fits text.
- Hover a child rectangle → tooltip (airport, island, elevation) and emphasise the hovered child's
  **siblings (same parent)** while dimming the rest; restore on mouse-out.

## Validation

| check | result |
|-------|--------|
| parents (islands) | 171 (expected 171) |
| children (airports) | 285 (expected 285) |
| null-parent rows excluded | 1019, not in the tree |
| spot check | Great Britain → 27 airports; all leaf values ≥ 0 |
| contract | D3 v7, `d3.hierarchy`/`d3.treemap`, colour by parent, no forbidden APIs, interaction (tooltip + sibling highlight), subtitle, complete HTML |

## Reproduce

```bash
cd experiments
python3 results/viz_codegen_treemap/render_treemap_reference.py \
  --mapping results/viz_codegen_treemap/mapping_airport.json \
  --data mondial_database/mondial_data.json \
  --out results/viz_codegen_treemap/airport_reference.html
```

## Status / next

- Reference done and validated. Qwen/Coder run deferred until Coder-32B (port 8004) is available.
- **Circle packing** is the sibling one_many chart: the same parent→child hierarchy, swapping
  `d3.treemap` for `d3.pack` — a small `chart_circlepack.md` block can reuse this cell's data prep.
- Remaining cells: `weak → line / stacked bar / spider`, `basic → bar / scatter / choropleth /
  word cloud`.
