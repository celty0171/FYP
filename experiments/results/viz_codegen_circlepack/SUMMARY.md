# viz_codegen_circlepack — Step 3 deterministic renderer (one_many → circle packing, D3 v7)

Fourth Step-3 cell, the sibling of the tree map: the **same** one_many parent→child hierarchy, with
`d3.pack` instead of `d3.treemap`. Layered prompt (`prompts/viz_codegen/base_d3v7.md` +
`chart_circlepack.md`). Same paradigm: the model writes `render(mapping, rows) -> HTML` once; data is
read at run time and never enters the prompt.

## Case and inputs

- Pattern `one_many_relationship`, case 7 (`airport`): child table `airport` with non-PK foreign key
  `island` → parent `Ep = island`; scalar child attribute `elevation`. Stage-1/2 also lists circle
  packing for this case (`prompt_v8_thinking/responses/case_7.json`).
- `mapping_airport.json` — `{table: airport, parent: island, child: iata_code, measure: elevation}`.
- Data: full `mondial_database/mondial_data.json`; renderer selects `data["tables"]["airport"]`.

## Renderer

`render_circlepack_reference.py` — D3 v7 (`d3.hierarchy` + `d3.pack`, core bundle, no plugin), std-lib
only, HTML by plain concatenation (no f-string / `str.format`). Construction:

- Builds the **same two-level hierarchy** as the tree map (root → island → airport; leaf value =
  `elevation`, floored at 0); **excludes null-parent rows** (1019 airports with `island = null`).
- `d3.pack().padding(3)`; draws parent **container circles** (depth 1) plus child **leaf circles**,
  coloured **by parent**; parent labels near the top of each container, child labels only when the
  circle fits text.
- Hover a child circle → tooltip (airport, island, elevation) and emphasise the hovered child's
  **siblings (same parent)** while dimming the rest; restore on mouse-out.

## Validation

| check | result |
|-------|--------|
| parents (islands) / children (airports) | 171 / 285 (as expected); 1019 null-parent excluded |
| layout | uses `d3.pack`, not `d3.treemap` |
| structure | D3 v7, `d3.hierarchy`, parent + leaf circles, colour by parent, no forbidden APIs |
| interaction / contract | tooltip + sibling highlight, subtitle, no f-string, complete HTML |

The one_many row of the taxonomy (tree map + circle packing) shares one data-prep recipe; only the
D3 layout call differs — confirming the chart blocks split cleanly by chart while reusing the
pattern's data transformation.

## Reproduce

```bash
cd experiments
python3 results/viz_codegen_circlepack/render_circlepack_reference.py \
  --mapping results/viz_codegen_circlepack/mapping_airport.json \
  --data mondial_database/mondial_data.json \
  --out results/viz_codegen_circlepack/airport_reference.html
```

## Status / next

- Reference done and validated. Qwen/Coder run deferred until Coder-32B (port 8004) is available.
- Remaining cells: `weak → line / stacked bar / spider`, `basic → bar / scatter / choropleth /
  word cloud`.
