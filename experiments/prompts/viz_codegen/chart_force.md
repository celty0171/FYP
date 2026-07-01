# Chart-specific instructions: Force-directed graph (reflexive_many_many and many_many)

## Pattern context

This renderer serves **both** relationship patterns — `reflexive_many_many_relationship` **and** `many_many_relationship`. The visualisation is a **force-directed node-link graph**: instances are nodes, relationships are links, and a physics simulation lays them out so that connected nodes are drawn together. Unlike the chord (which fixes every node on a circle) or the matrix (which fixes every node on a grid), the force layout reveals **topology** — clusters, hubs, bridges and disconnected components. It is the right complement for the **sparse** case (e.g. `borders`), where a chord shows connections but not community structure.

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

- `d3.forceSimulation(nodes)` with `forceLink(links).id(...)`, `forceManyBody()`, `forceCenter()`, and a small `forceCollide()`.
- **Determinism:** the base contract forbids run-time randomness in the *authoring*, but a live force simulation is seeded from node positions. Seed node `x`/`y` deterministically (e.g. on a circle by index) **before** the simulation, then either run a fixed number of `sim.tick()` iterations synchronously and draw the final positions, or run the animation from the seeded start. Do **not** rely on `Math.random` initial placement.
- Node radius by degree; node fill by group (bipartite) or by degree (reflexive). Link stroke-width by a `scaleSqrt` of `w`.

## Sizing so the whole graph is visible (mandatory)

A force simulation has **no bounding box**: charge repulsion and long links push peripheral nodes past the initial `width`/`height`, so those nodes (and their labels) are drawn outside the SVG viewport and clipped. You cannot know the final extent in advance. Two acceptable fixes, use at least one:

- add a **bounding force** or clamp each node's `x`/`y` into `[r, size − r]` on every tick so the layout stays inside a known box; **or**
- after the simulation settles, refit the root `<svg>` to its content: read `svg.node().getBBox()` and set the element's `viewBox` **and** `width`/`height` to that box expanded by a small pad (enough to cover node radii, strokes and labels).

The `getBBox` refit is the most robust and works whatever the data — do not rely on the host page to scroll or clip. Guard against `NaN` positions (a stray `NaN` makes `getBBox` throw): only draw once positions are finite.

## Layout & aesthetics

Aim for a clean, publication-quality figure, not merely a correct one:

- **Links** — thin lines, low opacity (≈ 0.2–0.5) so a busy graph reads as texture rather than a black mass; a neutral grey (`#999`) keeps the node colours dominant; width on a `scaleSqrt` of `w`. Straight lines are fine; gentle curves help when many links share endpoints.
- **Nodes** — radius on a `scaleSqrt` of degree with a sensible min/max (≈ 3–14 px); a thin white stroke separates overlapping circles; colour by **group** (two calm families) for bipartite, or by degree with a perceptually-uniform scale (e.g. `d3.interpolateViridis`) for reflexive. Draw nodes **after** links so they sit on top.
- **Spacing** — tune `forceManyBody` strength, `forceLink` distance and a `forceCollide(radius)` so nodes neither overlap nor fly apart; the graph should fill the frame without crowding.
- **Labels** — label only the salient nodes (e.g. the top-degree hubs, or on hover) rather than every node, which would be an unreadable smear; small muted font.
- **Legend & chrome** — for the bipartite case a short legend naming the two node families; a clear title plus one-line subtitle stating what node size and link width encode; muted greys for chrome.
- **Hover polish** — on node hover, lift the node, its incident links and neighbours and smoothly dim the rest; keep the tooltip compact and positioned from the pointer.

## Interactivity (per base contract)

Hovering a **node** shows a tooltip (instance name + degree) and highlights the node, its incident links and its neighbours while fading the rest. Hovering a **link** shows the pair and the encoded weight. Restore on mouse-out.

## Pitfalls to respect

- Namespace the two sides in the bipartite case, or an `E1` and an `E2` sharing a label collapse into one node and links break.
- `forceLink().id(d => d.id)` requires the ids you inject to match the `source`/`target` strings in the links exactly (after escaping) — keep them consistent.
- Do **not** assume nodes stay inside the initial `width`/`height` — the simulation pushes them out and they clip. Bound the layout or refit via `getBBox` (see *Sizing*).
- Read column names from the mapping only.
- A very large, dense graph (e.g. `is_member`) becomes a hairball — that is expected; the selector routes dense relations to the matrix, and force is offered as a secondary view. Still render faithfully; readability comes from filtering the data file, not from dropping edges here.
