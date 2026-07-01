# Chart-specific instructions: Arc diagram (reflexive_many_many only)

## Pattern context

This renderer serves **only** `reflexive_many_many_relationship` — a relationship whose two foreign keys reference the **same** entity set. The visualisation is an **arc diagram**: every instance is a point on a single ordered 1-D axis, and each relationship is a semicircular arc drawn above the axis between its two endpoints. On a linear axis, **short arcs** (local links between nearby nodes) and **long arcs** (long-range links) are immediately distinguishable — structure a chord obscures by wrapping the axis into a circle — and there is far less clutter than a chord at moderate N.

Do **not** use this renderer for `many_many_relationship`: two distinct entity sets do not share one axis, and are better served by the matrix, force graph or Sankey. The program must **reject** a `many_many` pattern with a clear error rather than draw something misleading.

## Mapping fields

```json
{ "table": "<relationship table>", "source": "<FK column>", "target": "<second FK column>",
  "value": "<scalar column name> | \"count\"", "pattern": "reflexive_many_many_relationship" }
```

- `source` / `target` — the two foreign-key columns, both drawing from the **same** instance set.
- `value` — arc thickness/opacity: a scalar column name, or the literal `"count"` (each edge weight 1). Falls back to legacy `width`, then to counting.
- Optional `title`.

## Required data transformation

1. Node set = the sorted union of all `source`/`target` values (one shared set).
2. Aggregate undirected edges: canonicalise each pair `(min, max)` index order so `(a,b)` and `(b,a)` collapse; drop self-loops (`a == b`); sum `value` or count per pair.
3. Compute each node's **unweighted degree** = the number of incident edges (neighbouring instances). Keep this separate from the arc-thickness measure: node size, colour and axis order use the degree **count**, never the summed `value` — otherwise the same measure is encoded twice and (for e.g. border length) node size spuriously tracks the scalar rather than connectivity.
4. **Order the axis by degree** (hubs first), not alphabetically — this pulls the high-degree nodes together and makes long-range links legible. Recompute each node's axis position after ordering and remap the link endpoints to the new positions.
5. Inject the ordered `names`, per-node `deg` (the unweighted count), and `links` (`{i, j, w}` as axis indices, `w` = the scalar `value`/count for arc thickness) via `json.dumps`.

## D3 v7 construction

- `d3.scalePoint()` (or a band) over the node index range for x-positions.
- Each arc is an SVG `path` using the elliptical-arc command: `M x1,baseY A r,r 0 0,1 x2,baseY` with `r = |x2 - x1| / 2` (a semicircle above the axis). Arc stroke-width from a `scaleSqrt` of `w`.
- Draw node circles on the axis (radius/colour by degree) and rotated text labels below.

## Sizing so the whole diagram is visible (mandatory)

Because each arc rises **above** the axis by its radius `r = span / 2`, the drawing's height is **not known until the layout is computed**. If you fix the axis near the top with a small constant margin, the top of every wide arc is drawn at a negative `y` — outside the SVG viewport — and is silently clipped (the classic "the upper half of the arc diagram is missing" bug). Size the canvas from the data instead:

- compute `maxR` = the largest `|x(i) − x(j)| / 2` over the **actual links** (the tallest arc);
- place the axis at `baseY = maxR + topPad`, so the tallest arc's apex lands at `y = topPad`, fully inside the canvas;
- reserve `labelSpace` **below** the axis for the rotated labels (≈ longest label length × font-width);
- set the SVG **height** to `baseY + labelSpace + bottomPad`, and the **width** to the axis span plus left/right padding.

As a final, general safeguard against any residual overflow (long labels, stroke widths), after all marks are drawn refit the root `<svg>` to its content: read `svg.node().getBBox()` and set the element's `viewBox` **and** `width`/`height` to that box expanded by a small pad. The structural sizing and the `getBBox` refit together guarantee the entire figure renders for any dataset — do not rely on the host page to scroll or clip.

## Layout & aesthetics

Aim for a clean, publication-quality figure, not merely a correct one:

- **Whitespace & margins** — generous, roughly symmetric padding; never let a mark or label touch the SVG edge.
- **Arcs** — no fill; `stroke-linecap: round`; a low base opacity (≈ 0.3–0.5) so overlapping arcs read as denser shading rather than one solid mass. A single calm hue (or a subtle sequential ramp keyed on `w`) looks better than a rainbow. Consider drawing the longest arcs first so short local arcs sit on top.
- **Nodes** — radius on a `scaleSqrt` of degree with a sensible min/max (≈ 2–10 px) so hubs stand out yet singletons stay visible; a thin white stroke keeps touching circles distinct; colour by degree with a perceptually-uniform scale (e.g. `d3.interpolateViridis`).
- **Labels** — small font (≈ 9–10 px), muted fill (`#333`), rotated 90° and anchored at the axis. When nodes are dense, **thin** the labels (show every k-th, or only nodes above a degree threshold) rather than letting them overlap into an unreadable smear; make sure `labelSpace` matches the longest label you actually draw.
- **Baseline** — a faint horizontal rule under the nodes gives the eye an anchor for the axis.
- **Typography & chrome** — a clear title plus a one-line subtitle stating what arc thickness and node size encode; consistent sans-serif; keep chrome in muted greys so the data dominates.
- **Hover polish** — on highlight, lift the active marks' opacity and smoothly dim the rest; keep the tooltip compact and positioned from the pointer.

## Interactivity (per base contract)

Hovering a **node** highlights its incident arcs and neighbour nodes (tooltip: name + degree). Hovering an **arc** highlights just that arc (tooltip: the two names + encoded weight). Restore on mouse-out.

## Pitfalls to respect

- Reject `many_many` explicitly; this chart is reflexive-only.
- Collapse undirected duplicates and drop self-loops before drawing.
- Order by degree, and remap link indices to the new order — a common bug is drawing arcs against the pre-sort indices.
- Do **not** fix the axis near the top with a constant small margin — arcs rise above it and are clipped. Size the height from the tallest arc (see *Sizing*).
- Read column names from the mapping only; never hard-code Mondial names.
