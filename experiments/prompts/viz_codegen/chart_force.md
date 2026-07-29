# Chart-specific instructions: Force-directed graph (reflexive_many_many and many_many)

## Pattern context

This renderer serves **both** relationship patterns — `reflexive_many_many_relationship` **and** `many_many_relationship`. The visualisation is a **force-directed node-link graph**: instances are nodes, relationships are links, and a physics simulation lays them out so that connected nodes are drawn together. Unlike the chord (which fixes every node on a circle) or the matrix (which fixes every node on a grid), the force layout reveals **topology** — clusters, hubs, bridges and disconnected components. It is the right complement for the **sparse** case, where a chord shows connections but not community structure.

Like the matrix, it does **not** require a scalar attribute — with none, links are weighted by edge `"count"`.

- `reflexive_many_many_relationship` — one node set; every node is an instance of the same entity type. Colour nodes by **degree** (a sequential scale) so hubs stand out.
- `many_many_relationship` — two node sets. **Namespace** the two sides (so an `E1` value and an `E2` value that happen to share a string are distinct nodes) and colour by **group** (two families) with a short legend, so the bipartite structure is legible.

Read the optional `pattern` field; if absent, infer bipartite when source/target value sets are disjoint.

## Mapping fields

```json
{ "table": "<relationship table>", "source": "<FK column>", "target": "<second FK column>",
  "value": "<scalar column name> | \"count\"", "pattern": "<reflexive_many_many_relationship | many_many_relationship>" }
```

- `source` / `target` — the two foreign-key columns.
- `value` — link weight: a scalar column name, or the literal `"count"` (each edge counts 1). Falls back to legacy `width`, then to counting. Collapse parallel edges, summing weights.
- Optional `title`.

## Library

`d3.forceSimulation` and the `d3.force*` helpers are part of the main **d3.v7.min.js** bundle — no extra plugin script is needed.

## Required data transformation

1. Build the node list. For *reflexive*, nodes = sorted union of source/target values. For *many_many*, nodes = namespaced sources (group 0) then namespaced targets (group 1); keep a clean display label separate from the namespaced id.
2. Build the link list: one link per distinct instance pair, `w` = summed `value` or edge count. For *reflexive* treat the pair as undirected (canonicalise the id order so `(a,b)` and `(b,a)` collapse).
3. Inject `nodes` (`{id, group}`) and `links` (`{source, target, w}`) via `json.dumps`. `d3.forceLink().id(d => d.id)` resolves string ids to node objects.

## D3 v7 construction

- `d3.forceSimulation(nodes)` with `forceLink(links).id(...)`, a **degree-scaled** `forceManyBody()`, gentle centring (`forceX`/`forceY` at low strength, or `forceCenter`), and a **padded** `forceCollide()`. See *Reducing overlap and clutter* below for how to tune these so a busy graph does not collapse into a hairball.
- **Determinism:** the base contract forbids run-time randomness in the *authoring*, but a live force simulation is seeded from node positions. Seed node `x`/`y` deterministically (e.g. on a circle by index) **before** the simulation, and do **not** rely on `Math.random` initial placement. Determinism comes from that fixed seed — **not** from stopping the simulation. **Prefer a live simulation** run from the seeded start with a `sim.on("tick")` handler, because drag (see *Interactivity*) needs it. Optionally pre-run a fixed number of synchronous `sim.tick()` iterations to settle the layout before the first paint, but keep the simulation **live** afterwards rather than `stop()`ping it and drawing a frozen, undraggable snapshot.
- Node radius by degree; node fill by group (bipartite) or by degree (reflexive). Link stroke-width by a `scaleSqrt` of `w`.

## Sizing so the whole graph is visible (mandatory)

A force simulation has **no bounding box**: charge repulsion and long links push peripheral nodes past the initial `width`/`height`, so those nodes (and their labels) are drawn outside the SVG viewport and clipped. You cannot know the final extent in advance. Two acceptable fixes, use at least one:

- **Preferred — refit after settling:** let the simulation spread **freely**, then read `svg.node().getBBox()` and set the element's `viewBox` **and** `width`/`height` to that box expanded by a small pad (enough to cover node radii, strokes and labels); **or**
- a **gentle bounding force** that pulls nodes toward the centre (`forceX`/`forceY` at low strength) if you need to keep the extent finite.

Do **not** hard-clamp each node's `x`/`y` into the *initial* `[r, size − r]` box on every tick: that piles nodes up against the edges and *defeats* the collision force, which is a leading cause of node overlap. Use a low-strength positional force for centring, and the `getBBox` refit to reveal whatever extent the layout actually reaches. Guard against `NaN` positions (a stray `NaN` makes `getBBox` throw): only draw once positions are finite.

## Reducing overlap and clutter (mandatory)

A force graph easily degenerates into an unreadable "hairball" of overlapping nodes, crossing links and colliding labels. Treat the following as layout **requirements**, not optional polish. Every rule is **data-agnostic** — the numeric force constants below (strengths, `distanceMax`, collide iterations) are **global defaults** applied to every graph, whereas any **data-dependent threshold** (how many labels to keep, what to filter) must be **derived from the graph itself** (node count, degree distribution); never hard-code a value that special-cases a particular relation:

- **Let the layout breathe.** Do not confine nodes to the initial box (see *Sizing*): free spreading plus the `getBBox` refit is what lets collision actually separate them.
- **Separate the two groups (bipartite).** For `many_many`, add a positional force that pulls the two node families toward opposite anchors — e.g. a `forceX` whose target is near **¼ of the width** for group 0 and **¾** for group 1. The separation only works if that force is **strong enough to win** the tug-of-war against the links and centring pulling the groups back together. Concretely: give the separation force a strength on the **same order as the link strength** — e.g. `forceX` strength ≈ **0.2–0.4** — while **weakening the link pull** to ≈ **0.1–0.2** and keeping any centre/`forceX(cx)` force weak (≤ ~0.05). A separation strength an order of magnitude below the link strength (e.g. 0.05 vs 0.4) is the usual reason the two groups still overlap in a central blob — if that happens, **raise the separation strength and lower the link strength** until two distinct columns form. This lightweight bipartite layout is the single biggest clutter win for two-set relations.
- **Push hubs apart.** Scale `forceManyBody` repulsion by degree (hubs repel harder), and **cap its reach** with a `distanceMax` on the order of the frame size, so a large graph stays stable instead of a few high-degree nodes blowing the layout apart (or, without a cap, everything repelling everything into an even smear). Give `forceCollide` a **padding** beyond the node radius with `.iterations(2)`, so no two circles overlap. Scale the `forceLink` **distance** by the endpoints' degree — shorter links for high-degree pairs — so hubs pull their neighbours in tight while the periphery is free to spread, which reads as clusters rather than one uniform blob.
- **Drop isolated nodes.** A node that takes part in no relationship (degree 0) is pure clutter — hide it and state the hidden count in the subtitle. This removes noise without dropping any edge.
- **Declutter labels.** Even top-degree labels collide once hubs cluster. After the layout settles, walk the candidate labels in **descending-degree order** and hide any whose bounding box overlaps one already kept, so surviving labels never sit on top of each other. Measure each box from the **rendered text** via `getBBox()` rather than estimating from character count — the estimate is coarse and lets labels overlap or hides too many. Re-run this declutter pass **every time the simulation settles** (e.g. on the `end` event), not only on first paint, so the labels stay unclustered after the user drags a node and the layout re-settles.

These are general graph-drawing techniques (positional/separation forces, collision with padding, density reduction, greedy label de-overlap); apply them by measuring the graph, not by naming any table.

## Layout & aesthetics

Aim for a clean, publication-quality figure, not merely a correct one:

- **Links** — thin lines, low opacity (≈ 0.2–0.5) so a busy graph reads as texture rather than a black mass; a neutral grey (`#999`) keeps the node colours dominant; width on a `scaleSqrt` of `w`. Straight lines are fine; gentle curves help when many links share endpoints.
- **Nodes** — radius on a `scaleSqrt` of degree with a sensible min/max (≈ 3–14 px); a thin white stroke separates overlapping circles; colour by **group** (two calm families) for bipartite, or by degree with a perceptually-uniform scale (e.g. `d3.interpolateViridis`) for reflexive. Draw nodes **after** links so they sit on top.
- **Spacing** — the visual goal is a graph that fills the frame without crowding: nodes neither overlapping nor flying apart. The specific force tuning that achieves it (degree-scaled `forceManyBody` with `distanceMax`, padded multi-iteration `forceCollide`, degree-scaled `forceLink` distance, and group separation) is specified once under *Reducing overlap and clutter* — follow it there rather than re-tuning here.
- **Labels** — label only the salient nodes (the top-degree hubs, plus the hovered node) rather than every node, which would be an unreadable smear; small muted font. Run the `getBBox` collision pass from *Reducing overlap and clutter* so even those few hub labels never overlap each other.
- **Legend & chrome** — for the bipartite case a short legend naming the two node families; a clear title plus one-line subtitle stating what node size and link width encode; muted greys for chrome.
- **Hover polish** — on node hover, lift the node, its incident links and neighbours and smoothly dim the rest; keep the tooltip compact and positioned from the pointer.

## Interactivity (per base contract)

- **Hover a node** — show a tooltip (instance name + degree) and highlight the node, its incident links and its neighbours while fading the rest.
- **Hover a link** — show the pair and the encoded weight. Restore on mouse-out.
- **Drag nodes (required).** Nodes must be draggable: attach a `d3.drag()` behaviour that pins the node via `fx`/`fy` while dragging and releases them (`fx = fy = null`) on end, so the user can pull a node out of a cluster to inspect it. A drag only works on a **live** simulation: keep the simulation running with a `sim.on("tick")` handler that repositions the marks each frame, and on drag-start give it a small `alphaTarget` and `restart()`. **Do not** freeze the layout into a one-off static draw — a pre-run, `stop()`ped simulation drawn once at final positions **cannot be dragged**. Reconcile this with determinism as noted under *D3 v7 construction*: the reproducibility comes from the **fixed seed positions**, not from stopping the simulation, so a live simulation seeded deterministically satisfies both.

## Pitfalls to respect

- Namespace the two sides in the bipartite case, or an `E1` and an `E2` sharing a label collapse into one node and links break.
- `forceLink().id(d => d.id)` requires the ids you inject to match the `source`/`target` strings in the links exactly (after escaping) — keep them consistent.
- Do **not** assume nodes stay inside the initial `width`/`height` — the simulation pushes them out and they clip. Bound the layout or refit via `getBBox` (see *Sizing*).
- Read column names from the mapping only.
- A very large, dense graph becomes a hairball — that is expected; the selector routes dense relations to the matrix, and force is offered as a secondary view. Still render faithfully; readability comes from filtering the data file, not from dropping edges here.
