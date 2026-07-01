# viz_codegen_arc — Step 3 deterministic renderer (arc diagram, D3 v7) — reflexive only

> **2026-07-01 — proposal v2 §7 third build.** Adds the **arc diagram**, the reflexive-only view from
> `relationship_viz_proposal_v2_charts_and_selector.md`: instances on one ordered axis, relationships
> as semicircular arcs above it. On a linear axis, local (short) vs long-range (long) links are
> distinguishable and clutter is lower than a chord at moderate N.

## What it does

`render_arc_reference.py` serves **only** `reflexive_many_many_relationship`; it **rejects**
`many_many` with a `ValueError` (two distinct sets do not share one axis — use matrix/force/Sankey).

- Node set = sorted union of the two FK columns (one shared set).
- Undirected edges collapsed (`(min,max)` index), self-loops dropped.
- Node size, colour and axis order use the **unweighted degree** (number of neighbouring instances),
  kept separate from the arc-thickness measure so the two do not double-encode (a country's node size
  reflects how many neighbours it borders, not its total border length). Axis **ordered by degree**
  (hubs first); link indices remapped to the new order.
- Arc width = `value` (scalar column) → `width` → edge `"count"`.

## Sizing (no clipping)

Arcs are semicircles rising **above** the axis by half their span, so the drawing's height is only
known after layout. The renderer computes `maxR` (the tallest arc) from the link spans, places the
axis at `baseY = maxR + topPad`, and sizes the SVG to `baseY + labelSpace + bottomPad` — so every arc
apex lands at `y ≥ topPad` and no arc is clipped off the top (an earlier version fixed the axis near
`y=40`, which clipped ~450px off wide arcs, e.g. merges_with). As a general belt-and-suspenders (shared
with the matrix and force cells) it then refits the root `<svg>` `viewBox`/size to `getBBox()` so any
mark — rotated labels included — is fully contained whatever the data.

## Contract & reuse

Standard `render(mapping, rows) -> HTML` + `--mapping/--data/--out`; exposes `_rows_for` (server uses
it) and the extended `_encoding` (`value → width → "count"`). Std-lib only, D3 v7 (`scalePoint` +
elliptical-arc `path`), plain string concatenation, hover highlights a node's incident arcs +
neighbours.

## Validation (Mondial, mondial_data.json)

- `borders` (reflexive, `length`) → 326 arcs, complete HTML, D3 v7, no forbidden APIs.
- `merges_with` (reflexive, `"count"`, no attribute) → 92 arcs — renders where Sankey/chord render
  nothing.
- Guard: `encompasses` (many_many) → `ValueError` as designed.

Layered prompt: `base_d3v7.md` + `chart_arc.md`. Mappings: `mapping_borders_arc.json`,
`mapping_merges_with_arc.json`.
