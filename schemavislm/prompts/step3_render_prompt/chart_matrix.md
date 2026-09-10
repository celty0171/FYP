# Chart-specific instructions: Adjacency-matrix heatmap (reflexive_many_many and many_many)

## Pattern context

This renderer serves **both** relationship patterns — `reflexive_many_many_relationship` **and** `many_many_relationship`. The visualisation is an **adjacency-matrix heatmap**: every possible pair of instances is a cell, and the cell colour encodes the strength of the relationship between that pair. A matrix is the complement of the node-link (Sankey/chord) reading: it has **no edge crossings**, shows every pair (including absent ones) explicitly, and stays legible when the relationship is **dense or large** (where a chord becomes a hairball). Row/column ordering (seriation) can reveal blocks.

The two patterns differ only in the shape of the matrix:

- `reflexive_many_many_relationship` — both foreign keys reference the **same** parent `E`. The matrix is a **square** adjacency matrix over the shared node set, and is **symmetric**: fill both `matrix[i][j]` and `matrix[j][i]` for each undirected edge.
- `many_many_relationship` — the two foreign keys reference **two different** parents `E1` (rows) and `E2` (columns). The matrix is a **rectangular `|E1|×|E2|` bipartite** matrix; do **not** make it square and do **not** mirror cells.

Read the optional `pattern` field from the mapping to choose the shape; if absent, infer the bipartite (`many_many`) case when the source and target value sets are **disjoint**, and the reflexive case otherwise.

## Mapping fields

```json
{ "table": "<relationship table>", "source": "<FK column>", "target": "<second FK column>",
  "value": "<scalar column name> | \"count\"", "pattern": "<reflexive_many_many_relationship | many_many_relationship>",
  "category": "<optional discrete edge attribute>" }
```

Never hard-code these names; always read them from the mapping at run time.

- `source` / `target` — the two foreign-key columns.
- `value` — the cell weight. It is **either** the name of a scalar relationship attribute, **or** the literal string `"count"`, in which case each edge contributes **1** and the cell shows how many rows connect the pair. For backward compatibility, if `value` is absent read the legacy `width` field; if that is also absent, fall back to counting. **This count fallback is the point of the matrix** — it renders relationships that have no scalar attribute at all (which Sankey/chord cannot).
- Optional `category` — a discrete edge attribute (e.g. a membership `type`). When present, compute the **dominant** category value per cell and show it in the tooltip; the cell colour still encodes `value`/count.
- Optional `title`.

## Required data transformation

1. Build the node index. **Ordering depends on the pattern:** *reflexive* — one entity set, sorted union of all `source` and `target` values, used for **both** rows and columns; *many_many* — rows = sorted `source` (E1) values, columns = sorted `target` (E2) values.
2. Aggregate an `value`/count into a cell keyed by `(rowIndex, colIndex)`. For `"count"`, add 1 per row; otherwise add the numeric `value`. For *reflexive*, also add to the transposed cell `(j, i)` (symmetry) unless `i == j`.
3. Emit only the non-empty cells (a sparse list of `{i, j, v[, cat]}`) — a dense `N×N` array is wasteful for large, sparse relations.

## D3 v7 construction

- Inject the `rowNames`, `colNames` arrays and the sparse `cells` list via `json.dumps`.
- Use `d3.scaleBand()` over the row/column index ranges for the grid, and one `rect` per non-empty cell.
- Colour with a **sequential** scale (`d3.scaleSequential(d3.interpolateYlGnBu)` or similar) domained on `[0, maxValue]`.
- Place rotated **column labels** across the top and **row labels** down the left; leave margins so labels are not clipped.
- Size cells adaptively (clamp a per-cell pixel size by the larger dimension) so both small and large (10 k-cell) matrices open in a browser.

## Sizing so the whole diagram is visible (mandatory)

The grid itself is bounded, but the **labels are not**: rotated column labels extend *upward* past the top edge and row labels extend *left* past the left edge. A fixed top/left margin clips the longest names (e.g. long organisation names as columns), so reserve margin from the data:

- **top margin** ≥ the longest **column** label's pixel length (rotated labels project their text length vertically); **left margin** ≥ the longest **row** label's pixel length; add a few px of breathing room.
- Then set the SVG **width** = `left margin + grid width + right pad` and **height** = `top margin + grid height + bottom pad`.

As a final, general safeguard for any residual overflow, after drawing refit the root `<svg>` to its content: read `svg.node().getBBox()` and set the element's `viewBox` **and** `width`/`height` to that box expanded by a small pad. Structural margins plus the `getBBox` refit guarantee the whole matrix — labels included — renders for any dataset; do not rely on the host page to scroll or clip.

## Layout & aesthetics

Aim for a clean, publication-quality figure, not merely a correct one:

- **Cells** — keep cells **square** (equal band widths on both axes) so the matrix reads as a grid; a hairline light-grey gap or 1 px white stroke between cells separates them without heavy borders. Do not stroke cells so thickly that colour is lost at small sizes. **Lopsided exception:** when the two sides differ greatly in cardinality (e.g. 240 rows × 6 columns), do **not** shrink both bands to the smaller side and crush the sparse axis into an unlabelable strip. Give every band a **minimum pixel size large enough for its (rotated) label**, allowing **rectangular** cells on the lopsided axis rather than forcing tiny squares — the small-cardinality axis (the 6 columns) must stay wide/tall enough to draw *every* one of its labels legibly.
- **Colour** — a **sequential, perceptually-uniform** scale (e.g. `d3.interpolateYlGnBu` / `Blues` / `Viridis`) domained on `[0, maxValue]`; render empty pairs as blank (no rect) or a very faint background, so present relationships pop. Always include a small **colour legend / key** naming what the colour encodes (the `value` column or "count").
- **Seriation** — order rows/columns so related nodes sit together (reuse the node ordering; degree- or cluster-based) — this surfaces blocks and diagonals instead of a random speckle.
- **Labels** — small font (≈ 9–10 px), muted fill (`#333`); when a side is dense, **thin** the tick labels (show every k-th) rather than overlapping them into a smear; make sure the reserved margin matches the longest label you actually draw. **Thin each axis independently**, using **only that axis's own** pixel length and band size — row labels from the grid **height**, column labels from the grid **width**. Never derive one shared `maxLabels` from `min(gridWidth, gridHeight)` and apply it to both axes: on a lopsided matrix (few columns, many rows) the narrow width then wrongly thins the *sparse* axis and silently drops most of its ticks (e.g. showing only 3 of 6 continents). An axis with few categories must show **every** label.
- **Whitespace & chrome** — generous outer padding; a clear title plus a one-line subtitle stating the framing (symmetric vs bipartite) and what colour encodes; muted greys for chrome so the data dominates.
- **Hover polish** — highlight the hovered cell's whole row + column smoothly and dim the rest; keep the tooltip compact and positioned from the pointer.

## Interactivity (per base contract)

Hovering a cell must show a tooltip with both instance names, the encoded `value`/count, and (if `category` is set) the dominant category; and emphasise the hovered cell's **entire row and column** while de-emphasising the rest, restoring on mouse-out.

## Pitfalls to respect

- Do **not** mirror cells in the bipartite (`many_many`) case; only the reflexive matrix is symmetric.
- When `value == "count"` (or no weight column exists), never try to parse a numeric column — count edges.
- Read column names from the mapping only; never hard-code Mondial names like `country`/`length`.
- Keep the cell list sparse; a full `N×N` allocation is quadratic and needless for large sets.
- Do **not** use a fixed top/left margin for labels — long names are clipped. Reserve margin from the longest label, or refit via `getBBox` (see *Sizing*).
