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
3. Compute each node's **unweighted degree** = the number of incident edges (neighbouring instances). Keep this separate from the arc-thickness measure: node size and colour use the degree **count**, never the summed `value` — otherwise the same measure is encoded twice and (for e.g. border length) node size spuriously tracks the scalar rather than connectivity.
4. **Order the axis to make every arc's span as short as possible.** The node order is the single biggest determinant of arc-diagram quality, on two fronts at once: short arcs mean **few crossings**, and — because the canvas height is set by the *tallest* arc — a small **maximum** span keeps the figure compact (a single long-range **"bridge"** arc otherwise balloons it into a tall, mostly-empty slab). So state the objective explicitly as **minimising arc spans**: both the **total** span `Σ|i−j|` (the *minimum linear arrangement* problem) and the **maximum** span `max|i−j|` (graph *bandwidth*). Do **not** order by degree (piles every hub at one end) or alphabetically (arbitrary); place **connected nodes adjacent**. Both objectives are NP-hard — approximate them with std-lib heuristics:

   - **Seed with a spectral (Fiedler) ordering.** Order the nodes by their value in the eigenvector of the **second-smallest** eigenvalue of the graph Laplacian `L = D − A`. This minimises `Σ w·(x_i − x_j)²`, which penalises long arcs **super-linearly** and so reliably avoids the whole-axis bridge. Compute it with std-lib power iteration: pick `c` ≥ the largest eigenvalue (e.g. `2·maxDeg + 1`) and iterate `x ← normalise(demean((cI − L)·x))`, where `demean` subtracts the mean to project out the all-ones vector (the eigenvalue-0 mode); once it settles, order nodes by `x`. Do this **per connected component** and concatenate the components (a disconnected graph has a degenerate global Fiedler vector, so a single global pass misplaces whole components at opposite ends). *(A **pseudo-peripheral** Reverse Cuthill-McKee order — BFS from a start chosen by BFS eccentricity — is an acceptable combinatorial alternative that also targets bandwidth. A plain min-degree-start RCM is **not** reliable: it can leave a bridge arc spanning almost the whole axis.)*
   - **Refine with barycenter iteration** (move each node to the weighted-mean position of its neighbours and re-sort). **Break ties on each node's current position, not its id** — id ties scramble locality and make the order oscillate, whereas the current position preserves the clusters the seed found. **Run enough passes to converge** (a few dozen; because you keep the best pass, extra passes never hurt — do not cap at ~5–10). Keep whichever pass gives the lowest total (weighted) span, so the result never regresses below the seed.

   Recompute each node's axis position after ordering and remap the link endpoints to the new positions.
5. Inject the ordered `names`, per-node `deg` (the unweighted count), and `links` (`{i, j, w}` as axis indices, `w` = the scalar `value`/count for arc thickness) via `json.dumps`.

## D3 v7 construction

- `d3.scalePoint()` (or a band) over the node index range for x-positions.
- Each arc is an SVG `path` using the elliptical-arc command: `M x1,baseY A r,r 0 0,<sweep> x2,baseY` with `r = |x2 - x1| / 2`. Draw the diagram **two-sided**: alternate arcs **above** (sweep `1`) and **below** (sweep `0`) the baseline — this halves the visual density on each side, since arcs on opposite sides can never overlap. Alternate by draw order (longest-first) so tall arcs are split between the sides. Arc stroke-width from a `scaleSqrt` of `w`.
- Draw node circles on the axis (radius/colour by degree) and rotated text labels below.

## Sizing so the whole diagram is visible (mandatory)

Because each arc rises **above** the axis by its radius `r = span / 2`, the drawing's height is **not known until the layout is computed**. If you fix the axis near the top with a small constant margin, the top of every wide arc is drawn at a negative `y` — outside the SVG viewport — and is silently clipped (the classic "the upper half of the arc diagram is missing" bug). Size the canvas from the data instead:

- compute each arc's apex height as `|x(i) − x(j)| / 2`, and take `maxR` = the tallest — **but cap it**. After a good crossing-minimising order almost every arc is short (small span), yet a graph can still contain one or two unavoidable long-range **"bridge"** links whose span is nearly the whole axis; a single such arc rises half the axis width and would balloon the canvas into a tall, mostly-empty slab that looks heavy and huge. Cap the apex height at a sensible maximum — e.g. a fraction of the axis width, or a modest multiple of a high span **percentile** (say the 95th) — draw the few over-tall arcs **flattened to that cap** (a shallower arc, i.e. an elliptical `A rx,ry` with a reduced `ry`, rather than a full semicircle), and use the **capped** height as `maxR`. This keeps the figure compact when the ordering has already made the vast majority of arcs short.
- because the diagram is **two-sided**, size each side from its own (capped) tallest arc — `topMaxR` and `botMaxR`. Place the axis at `baseY = topMaxR + topPad` so the tallest top-side arc's apex lands at `y = topPad`;
- reserve `botMaxR` **plus** `labelSpace` below the axis: the bottom-side arcs occupy `botMaxR`, then the rotated labels sit **below** them at `y = baseY + botMaxR + …` (≈ longest label length × font-width);
- set the SVG **height** to `baseY + botMaxR + labelSpace + bottomPad`, and the **width** to the axis span plus left/right padding.

As a final, general safeguard against any residual overflow (long labels, stroke widths), after all marks are drawn refit the root `<svg>` to its content: read `svg.node().getBBox()` and set the element's `viewBox` **and** `width`/`height` to that box expanded by a small pad. The structural sizing and the `getBBox` refit together guarantee the entire figure renders for any dataset — do not rely on the host page to scroll or clip.

## Layout & aesthetics

Aim for a clean, publication-quality figure, not merely a correct one:

- **Whitespace & margins** — generous, roughly symmetric padding; never let a mark or label touch the SVG edge.
- **Arcs** — no fill; `stroke-linecap: round`; a low base opacity (≈ 0.3–0.5) so overlapping arcs read as denser shading rather than one solid mass. **Default to a single fixed calm hue that is clearly visible** — a *mid-to-dark* muted blue or grey (e.g. around `#4477aa`), **never a pale tint**. If you encode `w` by colour, use a **single-hue** sequential ramp (not a multi-hue scheme such as `d3.interpolateCool`, `interpolateViridis` or any rainbow — those drift through cyan/green and look garish), **but clamp the ramp to its darker portion**: sequential ramps like `interpolateBlues` start at near-**white**, and that pale low end multiplied by the low stroke opacity renders those arcs almost invisible. Map `w` into roughly the **upper half** of the interpolator (e.g. `[0.4, 1.0]`, never the full `[0, 1]`) so even the lightest, thinnest arc stays legible against the background. Remember **light hue × low opacity = invisible** — sanity-check that the faintest arc is still clearly visible, and if in doubt prefer the single fixed hue over a ramp. Consider drawing the longest arcs first so short local arcs sit on top.
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
- Order the axis to **minimise arc spans** (total *and* maximum — not by degree, not alphabetically), and remap link indices to the new order — a common bug is drawing arcs against the pre-sort indices. Watch the **maximum** span specifically: a plain min-degree-start RCM can leave one whole-axis "bridge" arc that balloons the canvas even when every other arc is short — prefer a spectral (Fiedler) or pseudo-peripheral seed (see step 4).
- Do **not** fix the axis near the top with a constant small margin — arcs rise above it and are clipped. Size the height from the tallest arc (see *Sizing*).
- Read column names from the mapping only; never hard-code Mondial names.
