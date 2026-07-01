# viz_codegen_matrix — Step 3 deterministic renderer (adjacency-matrix heatmap, D3 v7)

> **2026-07-01 — proposal v2 §7 "first build".** Adds the **matrix heatmap**, the highest-value /
> lowest-risk chart from `relationship_viz_proposal_v2_charts_and_selector.md`: it serves **both**
> relationship patterns, has no edge crossings, scales to dense `is_member`, and — via the **count
> fallback** — unlocks the two relations that render nothing today (`is_member`, `merges_with` have
> no scalar width). Complements the node-link family (Sankey/chord) rather than replacing it.

## What it does

`render_matrix_reference.py` reads the relationship mapping and draws a `d3.scaleBand` + `rect`
heatmap, one cell per non-empty instance pair, coloured by a sequential scale.

- **reflexive** (`borders`, `merges_with`) — square symmetric adjacency matrix over the sorted union
  node set; both `(i,j)` and `(j,i)` filled per undirected edge.
- **many_many** (`encompasses`, `is_member`) — rectangular `|E1|×|E2|` bipartite matrix, rows =
  `source`, cols = `target`; never mirrored.

## Cell value (the count fallback)

`mapping["value"]` is **either** a scalar column name **or** the literal `"count"`; falls back to the
legacy `width`, else counts edges. `"count"` makes the matrix work with **no scalar attribute**,
which is exactly why the proposal picks it first. Optional `mapping["category"]` (e.g. `is_member.type`)
adds the per-cell dominant category to the tooltip; colour still encodes value/count.

## Contract & reuse

Same `render(mapping, rows) -> HTML` + `--mapping/--data/--out` CLI as every viz cell; exposes
`_rows_for` (copied verbatim from `viz_codegen_chord`, used by the web server) and an **extended**
`_encoding` that resolves `value → width → "count"`. Std-lib only, D3 v7, plain string concatenation
(no brace-templating), hover highlights the cell's whole row + column.

## Validation (Mondial, mondial_data.json)

- `is_member` (many_many, `value:"count"`, `category:"type"`) → 10 087 cells, complete HTML, D3 v7,
  no forbidden APIs. `mapping_is_member_matrix.json`.
- `borders` (reflexive, `value:"length"`) → 652 cells = 326 edges × 2 (symmetric).
  `mapping_borders_matrix.json`.
- `merges_with` (reflexive, `value:"count"`, no attribute) → 184 cells = 92 × 2. Renders where
  Sankey/chord render nothing. `mapping_merges_with_matrix.json`.

Layered prompt: `prompts/viz_codegen/base_d3v7.md` + `prompts/viz_codegen/chart_matrix.md`.
