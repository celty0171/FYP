# viz_codegen_force — Step 3 deterministic renderer (force-directed graph, D3 v7)

> **2026-07-01 — proposal v2 §7 second build.** Adds the **force-directed graph**, the *topology*
> view from `relationship_viz_proposal_v2_charts_and_selector.md`: clusters, hubs, bridges and
> components that neither chord nor matrix expose. Serves **both** relationship patterns and, like the
> matrix, works with **no scalar** (edge `"count"` fallback). The selector offers it for the sparse
> case (`borders`) and as a secondary view elsewhere.

## What it does

`render_force_reference.py` builds a node/link graph and lays it out with `d3-force` (part of the main
d3.v7 bundle — no extra plugin).

- **reflexive** (`borders`, `merges_with`) — one node set, sorted union; nodes coloured by **degree**
  (hubs stand out); undirected links collapsed.
- **many_many** (`encompasses`) — two node sets, **namespaced** (`s::`/`t::`) so equal strings on the
  two sides stay distinct; coloured by group (blue/orange) with a legend.

Link weight is `value` (scalar column) → `width` → edge `"count"`; parallel edges summed.

## Determinism

A live force simulation is position-seeded: node `x`/`y` are placed on a circle by index **before**
the run, and the simulation is ticked a fixed 300 iterations synchronously, so the drawn layout is
reproducible across runs (no `Math.random` seeding).

## Contract & reuse

Standard `render(mapping, rows) -> HTML` + `--mapping/--data/--out`; exposes `_rows_for` (server uses
it) and the extended `_encoding` (`value → width → "count"`). Std-lib only, D3 v7, plain string
concatenation, hover highlights a node's incident links + neighbours.

## Validation (Mondial, mondial_data.json)

- `borders` (reflexive, `length`) → 169 nodes / 326 links.
- `merges_with` (reflexive, `"count"`, no attribute) → 56 nodes / 92 links — renders where
  Sankey/chord render nothing.
- `encompasses` (many_many, `percentage`) → 252 nodes (246 countries + 6 continents) / 251 links,
  bipartite colouring + legend.

All complete HTML, D3 v7, no forbidden APIs. Layered prompt: `base_d3v7.md` + `chart_force.md`.
Mappings: `mapping_borders_force.json`, `mapping_merges_with_force.json`, `mapping_encompasses_force.json`.
