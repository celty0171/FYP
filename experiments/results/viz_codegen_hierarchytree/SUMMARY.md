# viz_codegen_hierarchytree — Step 3 deterministic renderer (one_many_relationship → hierarchy tree, D3 v7)

The node-link chart of the `one_many_relationship` row, completing that row alongside the tree map
(`viz_codegen_treemap/`) and circle packing (`viz_codegen_circlepack/`). Layered prompt
(`base_d3v7.md` + `chart_hierarchytree.md`). Same paradigm: the renderer is written once; data is read
at run time and never enters the prompt.

## Strictly per the paper

pattern_notes / the McBrien paper: "Hierarchy tree: use when instances of parent entity `Ep` should be
shown as **nodes connected by lines** to child instances `Ec`. A discrete attribute `a1` may
**optionally** be used to colour the **links** between the entities." The mandatory-checks line is
explicit that, unlike tree map / circle packing, this chart is **not** an area encoding: "Hierarchy
tree does not require scalar size, but may use a discrete attribute for colour." So this renderer:

- reads **no measure** — `parent` (`kp`, the FK column) and `child` (`kc`) only, plus an **optional**
  `color` discrete attribute;
- colours the **parent→child links** (not the node fills) by that attribute when present, else neutral
  grey, with a legend only when `color` is given;
- imposes **no node cap** — the paper sets no completeness/size limit for this chart (that was a
  weak-entity concern), so the whole parent→child tree is drawn and the SVG is sized from the laid-out
  extent.

## Inputs

- `mapping_airport.json` — `{table: airport, parent: island, child: iata_code}` (the same one-many
  selection the tree map / circle packing use; here no measure is needed). Optional `color` (e.g.
  `country`) colours the links.
- Data: `mondial_database/mondial_data.json` → `data["tables"]["airport"]`.

## Renderer

`render_hierarchytree_reference.py` — std-lib only, HTML by plain concatenation. Builds a two-level
hierarchy (synthetic root → distinct `parent` values → child rows; rows with a null parent dropped),
lays it out with `d3.hierarchy` + `d3.tree().nodeSize(...)` (horizontal tidy tree), draws links with
`d3.linkHorizontal()` and a circle+label per node. Hover a node → emphasise its connected links
(parent's links to its children, or a leaf's link up) + tooltip (parent shows child count; leaf shows
its parent and the colour value if any).

## Validation (structural — pixels need a browser)

171 parents (islands), 285 children (airports), 457 nodes; `d3.hierarchy` + `d3.tree` + `linkHorizontal`;
optional-colour path verified (`color: country` → leaves carry `_color`, subtitle notes "Links coloured
by country", legend emitted); interaction present; complete HTML; no forbidden v6+ APIs; no f-string.
End-to-end through `web_pipeline`: `airport` one-many selection → recommends tree map / circle packing /
hierarchy tree, all three render with `available=True`.

## Reproduce

```bash
cd experiments
python3 results/viz_codegen_hierarchytree/render_hierarchytree_reference.py \
  --mapping results/viz_codegen_hierarchytree/mapping_airport.json \
  --data mondial_database/mondial_data.json \
  --out results/viz_codegen_hierarchytree/airport_reference.html
```

## Status

This is the **last** Step-3 cell in the taxonomy. All 5 patterns × 15 charts now have renderers wired
into `web_pipeline`; no chart Step 2 recommends returns "working in process" any more.
