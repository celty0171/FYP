# Proposal (Version 1) — Extend the pattern taxonomy for relationship visualisations

*Scope: the `many_many_relationship` and `reflexive_many_many_relationship` patterns. This version
**adds new schema patterns** to the VizER taxonomy so that each new chart is licensed by a named
pattern, in keeping with the McBrien–Poulovassilis "pattern → visualisation" philosophy. Version 2 is
the lighter-touch alternative (no taxonomy change; a Step-2 selector instead).*

## 1. Motivation

Sankey and chord are both **node-link** readings of the same object. Structurally, both relationship
patterns are a *weighted graph*: many-many is a weighted **bipartite** graph (an `E1 × E2` matrix);
reflexive is a weighted graph on **one** node set (a square adjacency matrix). The graph-drawing
literature (matrix vs node-link readability) is clear that node-link wins for *sparse, small* graphs
and collapses into a hairball for *dense or large* ones, where a **matrix** view wins. So the taxonomy
is currently missing whole families of view — and, as the audit below shows, it cannot render two of
the four real Mondial relationships at all.

## 2. Evidence from the Mondial schema (audit of every true m–m / reflexive relation)

| table | current pattern | sides (distinct) | edges | density | rel. attribute | symmetric | groupable endpoint |
|-------|-----------------|------------------|-------|---------|----------------|-----------|--------------------|
| `borders` | reflexive | ≈169 countries | 326 | **0.02** | `length` (scalar) | yes | country → continent |
| `merges_with` | reflexive | 35 / 44 seas | 92 | 0.06 | **none** | yes | sea → ocean (weak) |
| `encompasses` | many_many | 246 × 6 | 251 | 0.17 | `percentage` (scalar) | n/a | continent *is* a side |
| `is_member` | many_many | 237 × 169 | **10 087** | **0.25** | `type` (**categorical**) | n/a | org by category |

Findings that drive the design:

1. **Density spans 0.02 → 0.25.** `borders` is sparse (node-link is the right call); `is_member` is
   large *and* dense — Sankey/chord are an unreadable hairball there, but a matrix shows all 10 k cells.
2. **Coverage gap.** `is_member` and `merges_with` have **no scalar width**, so the current charts
   (which require `a1`) produce *nothing*. A matrix / force / arc keyed on **edge count** or a
   **categorical** attribute renders them.
3. **A real categorical edge attribute exists** (`is_member.type`, 31 values, dominated by `member`).
4. **No relationship carries a temporal attribute**, and **both reflexive relations are symmetric** —
   so the *temporal* and *directed-reflexive* refinements below are **not exercised by Mondial** and are
   proposed as future work, not built now.
5. **A grouping path exists** (`country → continent`), so the *grouped* refinement is feasible.

## 3. Proposed new patterns

Two of the relationship patterns are split by **schema-detectable** structure (so Step 1 stays blind
and deterministic). Properties that are only knowable from the rows (symmetry, density) are **not**
new patterns — they remain Step-2 selector signals (§4), because a schema-pattern classifier should
not depend on instance data.

| new pattern | parent | schema trigger | licensed charts |
|-------------|--------|----------------|-----------------|
| `weighted_many_many` / `weighted_reflexive` | m–m / reflexive | a scalar relationship attribute is present | Sankey, chord (as today) **+ weighted matrix heatmap** |
| `unweighted_many_many` / `unweighted_reflexive` | m–m / reflexive | **no** scalar attribute | **count matrix heatmap, force-directed graph, arc diagram** (encode by edge count) |
| `attributed_relationship` | m–m / reflexive | a **categorical** relationship attribute is present | **categorical matrix** (colour = category), **faceted small-multiples** (one panel per category), **parallel sets** |
| `grouped_relationship` | m–m / reflexive | an endpoint entity carries a grouping FK / categorical level | **hierarchical edge bundling**, **aggregated (group-level) chord / matrix** |
| *(future)* `temporal_relationship` | m–m / reflexive | a temporal relationship attribute | animated network, alluvial-over-time, streamgraph |

These compose: `is_member` is `unweighted_many_many` **and** `attributed_relationship` (categorical
`type`) **and** `grouped_relationship` (orgs by category) → it would be offered the count/categorical
matrix, faceted multiples, and parallel sets — exactly the views it needs and cannot get today.

## 4. New chart catalogue (Step 3 renderers, on the existing layered prompt base)

| chart | serves | what it adds over Sankey/chord | D3 |
|-------|--------|--------------------------------|----|
| **Adjacency-matrix heatmap** | both | every pair as a cell, exact value by colour, **no edge crossings**; row/col **seriation** reveals blocks/communities; scales to dense `is_member` | `scaleBand` + `rect` + sequential colour (reuse the Sankey affinity-ordering code) |
| **Force-directed graph** | both (bipartite force for m–m) | topology: clusters, hubs, bridges, components — chord's circle destroys these | `d3-force` |
| **Arc diagram** | reflexive | local vs long-range links along an ordered 1-D axis; far less clutter than chord at moderate N | path arcs |
| **Hierarchical edge bundling** | grouped | bundles edges along the group hierarchy → readable where chord is a mess | `d3.cluster` + `curveBundle` + `lineRadial` |
| **Parallel sets / alluvial** | attributed / multi-categorical | multi-way categorical flow across >2 axes (Sankey is only 2) | `d3-sankey` extended |

Data-derived selection signals (used *after* the pattern is fixed, to pick among a pattern's charts):
**N**, **density** `|edges| / (|E1|·|E2|)`, and **symmetry** (share of mutual pairs). These are measured
from the same instance rows Step 3 renders — the precedent already set for weak-entity completeness.

## 5. Pipeline impact

- **Step 1 (classifier):** add the schema-level refinements (`weighted/unweighted`, `attributed`,
  `grouped`). All are derivable from roles + SQL types, so Step 1 stays blind. Symmetry/density stay out.
- **Step 2 (recommend + map):** map each refined pattern to its chart group; use N/density/symmetry to
  order the recommendations. Mapping field names are fixed by the new renderers.
- **Step 3:** one new renderer per chart on the shared `base_d3v7.md`; the matrix renderer reuses the
  Sankey seriation.

## 6. Trade-off vs Version 2

Version 1 is the more **principled** and publishable contribution — a richer *pattern language* in which
each visualisation is justified by a named structural pattern, and it exposes the coverage gap as a
taxonomy gap. The cost is a more complex classifier and a larger taxonomy to validate. If the goal is to
**ship charts quickly with minimal disruption**, Version 2 (selector only) is the safer route.

## 7. Recommended first build (either version)

1. **Adjacency-matrix heatmap** + the density/N rule — highest value, lowest risk, literature-backed,
   serves both patterns, reuses existing code, and **unlocks `is_member` and `merges_with`**.
2. **Force-directed graph** for the sparse case (`borders`) — the topology view chord cannot give.
3. **Hierarchical edge bundling** + the `grouped_relationship` pattern — the best "new pattern + new
   viz" story, and Mondial's `country → continent` supports it.
