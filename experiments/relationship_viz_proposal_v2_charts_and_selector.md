# Proposal (Version 2) — Add charts and a selector, keep the six patterns

*Scope: the `many_many_relationship` and `reflexive_many_many_relationship` patterns. This version
**leaves the taxonomy unchanged** (Step 1 still emits the six patterns) and instead adds new Step-3
renderers plus a deterministic **Step-2 selector** that picks among them from structural and data
signals. Version 1 is the alternative that promotes those signals to named patterns.*

## 1. Motivation

Sankey and chord are both **node-link** readings of one object: structurally, many-many is a weighted
**bipartite** graph (an `E1 × E2` matrix) and reflexive is a weighted graph on **one** node set (a
square adjacency matrix). Node-link views are good for *sparse, small* graphs and become an unreadable
hairball for *dense or large* ones, where a **matrix** view wins. The current taxonomy offers only the
node-link family — and, as the audit shows, it cannot render two of the four real Mondial relationships
at all. We can close both gaps **without touching Step 1**: add the missing charts and a rule that
chooses between them.

## 2. Evidence from the Mondial schema (audit of every true m–m / reflexive relation)

| table | pattern | sides (distinct) | edges | density | rel. attribute | symmetric | groupable endpoint |
|-------|---------|------------------|-------|---------|----------------|-----------|--------------------|
| `borders` | reflexive | ≈169 countries | 326 | **0.02** | `length` (scalar) | yes | country → continent |
| `merges_with` | reflexive | 35 / 44 seas | 92 | 0.06 | **none** | yes | sea → ocean (weak) |
| `encompasses` | many_many | 246 × 6 | 251 | 0.17 | `percentage` (scalar) | n/a | continent *is* a side |
| `is_member` | many_many | 237 × 169 | **10 087** | **0.25** | `type` (**categorical**) | n/a | org by category |

Findings that drive the selector:

1. **Density spans 0.02 → 0.25.** `borders` is sparse (keep node-link); `is_member` is large *and*
   dense — Sankey/chord are a hairball, a **matrix** shows all 10 k cells.
2. **Coverage gap.** `is_member` and `merges_with` have **no scalar width**, so today's charts (which
   require `a1`) render *nothing*. A matrix / force / arc keyed on **edge count** or a **categorical**
   attribute renders them.
3. **A real categorical edge attribute** exists (`is_member.type`, 31 values).
4. **No relationship carries a temporal attribute**, and **both reflexive relations are symmetric** —
   so temporal and directed-reflexive handling are out of scope for Mondial (future work).
5. **A grouping path exists** (`country → continent`) → bundling is feasible.

## 3. New chart catalogue (Step 3 renderers, on the existing layered prompt base)

| chart | serves | what it adds over Sankey/chord | D3 |
|-------|--------|--------------------------------|----|
| **Adjacency-matrix heatmap** | both | every pair as a cell, exact value by colour, **no edge crossings**; row/col **seriation** reveals blocks; scales to dense `is_member`; works on **count** when there is no scalar | `scaleBand` + `rect` + sequential colour (reuse Sankey affinity-ordering) |
| **Force-directed graph** | both | topology: clusters, hubs, bridges, components | `d3-force` |
| **Arc diagram** | reflexive | local vs long-range links on an ordered 1-D axis; less clutter than chord at moderate N | path arcs |
| **Hierarchical edge bundling** | grouped endpoints | bundles edges along the group hierarchy | `d3.cluster` + `curveBundle` + `lineRadial` |
| **Parallel sets / alluvial** | categorical edge attr | multi-way categorical flow across >2 axes | `d3-sankey` extended |

## 4. The Step-2 selector (the core of this version)

For a relationship pattern, Step 2 measures a handful of **deterministic** signals and recommends a
ranked set of charts. Schema signals come from roles + SQL types; data signals are measured from the
same instance rows Step 3 reads (the precedent already set for weak-entity completeness).

Signals:

- `has_scalar` — a scalar relationship attribute exists (Sankey/chord/weighted-matrix usable).
- `has_categorical` — a discrete relationship attribute exists (categorical matrix / parallel sets).
- `groupable` — an endpoint entity has a grouping FK / categorical level (bundling).
- `N` — size of the larger node set.
- `density = |edges| / (|E1| · |E2|)`.
- `symmetric` — share of mutual `(a,b)/(b,a)` pairs ≈ 1 (reflexive only).

Selection rules (deterministic, ordered):

| condition | recommend (in order) |
|-----------|----------------------|
| sparse & small (`density` low, `N` small) & `has_scalar` | Sankey / chord (as today) → force graph → arc (reflexive) |
| dense **or** large (`density` high or `N` large) | **matrix heatmap** first → force graph |
| `not has_scalar` but `has_categorical` | **categorical matrix** → parallel sets → faceted small-multiples |
| `not has_scalar` and `not has_categorical` | **count matrix** → force graph → arc |
| `groupable` | add **hierarchical edge bundling** (and group-aggregated chord/matrix) |
| reflexive & `symmetric` | symmetric matrix / chord / arc |
| reflexive & **not** `symmetric` | directed force graph / asymmetric matrix (Mondial: not triggered) |

Worked examples: `borders` (sparse, scalar, symmetric, groupable) → chord/Sankey + arc + force +
bundling-by-continent. `is_member` (dense, **no scalar**, categorical, large) → **categorical matrix**
+ parallel sets — neither available today. `merges_with` (no attribute) → **count matrix** + force.

## 5. Pipeline impact

- **Step 1:** unchanged — still the six blind patterns.
- **Step 2:** one new function computing the signals above and the rule table; emits the existing
  `{table, source, target, width, pattern}` mapping plus, for the matrix, an optional `value` that may
  be a scalar column **or** the literal `"count"`, and an optional `category` for the categorical view.
- **Step 3:** one new renderer per chart on the shared `base_d3v7.md`; the matrix reuses the Sankey
  seriation. The existing Sankey/chord renderers are untouched.

## 6. Trade-off vs Version 1

Version 2 is the **lower-risk, faster** route: Step 1 stays blind and frozen, all the intelligence sits
in one Step-2 selector, and we can ship the matrix immediately. The cost is conceptual: the
"pattern → visualisation" mapping becomes one-pattern-to-many-charts decided by a rule table, rather
than each chart being licensed by a named structural pattern (Version 1's stronger research story).

## 7. Recommended first build (either version)

1. **Adjacency-matrix heatmap** + the density/N rule — highest value, lowest risk, literature-backed,
   serves both patterns, reuses existing code, and **unlocks `is_member` and `merges_with`**.
2. **Force-directed graph** for the sparse case (`borders`) — the topology view chord cannot give.
3. **Hierarchical edge bundling** for `groupable` relationships — Mondial's `country → continent`
   supports it.
