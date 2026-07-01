# Chart-specific instructions: Sankey diagram (many_many and reflexive_many_many)

## Pattern context

This renderer serves **both** relationship patterns — `many_many_relationship` **and** `reflexive_many_many_relationship` — a relationship table whose two foreign keys define a flow whose width is a scalar relationship attribute. The visualisation is a **Sankey diagram**: source instances are left-hand nodes, target instances are right-hand nodes, and the scalar attribute sets the width of the flow between them.

- For `many_many_relationship` the two foreign keys reference **two separate** parent entities `E1` (sources, left) and `E2` (targets, right): the two columns of nodes are genuinely different entity sets.
- For `reflexive_many_many_relationship` both foreign keys reference the **same** parent `E`. A Sankey draws this as a **directed** flow: the same instance may appear both as a left-hand source node and as a right-hand target node. That is correct and expected — the left column is "as source", the right column is "as target".

Because the **namespacing** below (`src:` / `tgt:`) already keeps the two sides as distinct node identities, **one renderer handles both patterns unchanged**: it does not need to branch on the pattern to be correct. Read the optional `pattern` field from the mapping only to phrase the subtitle (two entity sets vs. the same set on both sides); if it is absent, you may infer the reflexive case when the source and target value sets overlap.

## Mapping fields

The mapping names a table and three columns, by **role** — fill them from the actual selection; the
values below are placeholders, not fixed names. This renderer must work for **any** many-many
selection, not one specific table:

```json
{ "table": "<relationship table>", "source": "<FK column>", "target": "<second FK column>", "width": "<scalar relationship attribute>", "pattern": "<many_many_relationship | reflexive_many_many_relationship>" }
```

Never hard-code these names; always read them from the mapping at run time.

- `table` names the relationship table to read from the grouped database (see the base contract's data section).
- `source` is the first foreign key (`k1`), `target` the second (`k2`). For `many_many` these come from **two different** entity sets, so a value typically appears only as a source or only as a target; for `reflexive` they come from **one** set, so a value may appear on both sides.
- `width` is the scalar relationship attribute `a1` that sets flow thickness.
- Optional `pattern` (which of the two patterns this is) and `title`.

## Required data transformation

Sankey is driven by a `nodes` array and a `links` array:

1. Build the `nodes` array. Because `E1` and `E2` are different entities, **namespace** the node identities so a source value and a target value that happen to share a string are not merged (e.g. id `"src:" + source` and `"tgt:" + target`, with a display label of the bare value).
2. Build the `links` array: one link per `(source, target)` pair with `value = width`. Sum the widths of rows that share the same `(source, target)` pair into a single link (links must be unique per pair).

## D3 v7 construction

- Load the official plugin too: `<script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12/dist/d3-sankey.min.js"></script>`.
- Build the layout with `d3.sankey()` configured with `.nodeId(d => d.name)` (or numeric indices) so string ids resolve, plus `.nodeWidth(...)`, `.nodePadding(...)`, and `.extent(...)`.
- Draw link paths with `d3.sankeyLinkHorizontal()`; set each link's stroke-width to its laid-out `width`.
- Draw node rectangles and place a text label beside each node (labels on the right for left-side nodes and on the left for right-side nodes so they don't overlap the flows).
- Interaction (per the base contract): hovering a node highlights the flows touching it (`link.source === d || link.target === d`) and dims the rest, with a tooltip of the node label and its total flow; hovering a link shows `source.label → target.label (value)`.

## Layout — minimise link crossings (overlap reduction)

Dense Sankeys become unreadable when links overlap. What matters is the **number of link crossings**, not link length; in a single-column-order Sankey some crossings are topologically unavoidable (a source whose weight is mostly in one target but with a minor link to a non-adjacent target). The goal is not "zero overlap": minimise crossings by ordering, then make the residual traceable. Apply this deterministic, data-agnostic ordering **before drawing**:

- **Step A — order targets by affinity.** Build a target–target affinity matrix: for every pair of targets, sum over the sources that link to **both** the quantity `min(w_to_Ti, w_to_Tj)`. Seriate the targets so high-affinity targets are **adjacent** (greedy nearest-neighbour chaining on the affinity matrix, or spectral ordering), tie-broken by descending incoming weight then label. Give each target an integer rank, top → bottom.
- **Step B — order sources by barycentre.** For each source, `barycentre = Σ(weight · target_rank) / Σ(weight)`. Sort sources by barycentre, then descending total outgoing weight, then label. This clusters sources that flow to the same target. Do **not** force multi-target sources to group boundaries — let the barycentre place them.
- **Step C — order links.** Within a source, order links by target rank; within a target, by source rank.

Drive d3-sankey with the result: attach the computed integer `order` to every node and set `.nodeSort((a, b) => d3.ascending(a.order, b.order))`, `.linkSort((a, b) => (a.target.order - b.target.order) || (a.source.order - b.source.order))`, `.nodeAlign(d3.sankeyLeft)`, and a generous `.iterations(...)`.

## Visual design

- Use enough vertical height for the number of source nodes — do not compress a large Sankey into a short canvas; use generous `nodePadding` and a moderate `nodeWidth`.
- Colour links by their **target group** so overlapping links stay distinguishable; use partial link opacity so dense bundles remain readable.
- Draw links in **ascending weight order** (thin minor links on top) so a thin secondary link is not buried under a thick bundle. Do not hide links by reordering nodes.
- Place labels so they do not sit on dense bundles; on hovering a node, fade the links not connected to it so any single source's links (including its unavoidable cross-group link) can be traced.
- Add a subtitle stating what link width represents.

## Pitfalls to respect

- Keep the source side and target side as **separate node identities** (namespacing `src:` / `tgt:`) so a shared string does not collapse a left node and a right node into one. For `many_many` the two sets are genuinely disjoint; for `reflexive` the same instance legitimately appears on both sides as two namespaced nodes (its "as source" and "as target" roles) — do **not** merge them into a single node, or the directed flow collapses. (Contrast with the chord renderer, where the two sides share one circular node set.)
- Match the API to the loaded versions: `d3.v7.min.js` with `d3-sankey@0.12`. Do not use deprecated `sankey.link()` / `sankey.layout()` (older d3-sankey) or any `d3.keys`/`d3.nest`/`d3.event` removed in v6+.
- Bind the flow value to the mapped `width` column; do not invent a uniform weight.
