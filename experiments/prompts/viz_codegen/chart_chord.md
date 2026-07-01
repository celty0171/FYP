# Chart-specific instructions: Chord diagram (reflexive_many_many and many_many)

## Pattern context

This renderer serves **both** relationship patterns — `reflexive_many_many_relationship` **and** `many_many_relationship`. The visualisation is a **chord diagram**: instances sit around a circle and a scalar relationship attribute sets the width of the ribbon connecting a pair of them. The two patterns differ only in the node set:

- `reflexive_many_many_relationship` — both foreign keys reference the **same** parent `E`. Every point around the circle is an instance of the *same* entity type, and ribbons may connect any two of them (including, in principle, an instance to itself).
- `many_many_relationship` — the two foreign keys reference **two different** parents `E1` (sources) and `E2` (targets). The circle then holds **both** entity sets and the chord is **bipartite**: every ribbon runs between an `E1` instance and an `E2` instance, never within a group. Keep the two groups as **contiguous arcs** (all `E1` instances, then all `E2` instances) and **colour by group** so the two entity types are visually distinct.

Both cases are built from the same `N×N` matrix machinery below; they differ only in node ordering and colouring. Read the optional `pattern` field from the mapping to choose the framing; if it is absent, infer the bipartite (`many_many`) case when the source and target value sets are **disjoint**, and the reflexive case otherwise.

## Mapping fields

The mapping names a table and three columns, by **role** — fill them from the actual selection; the
values below are placeholders, not fixed names. This renderer must work for **any** reflexive
many-many selection, not one specific table:

```json
{ "table": "<relationship table>", "source": "<FK column>", "target": "<second FK column>", "width": "<scalar relationship attribute>", "pattern": "<reflexive_many_many_relationship | many_many_relationship>" }
```

Never hard-code these names; always read them from the mapping at run time.

- `source` and `target` are the two foreign-key columns of the relationship (`k1` and `k2`). For `reflexive` they draw from **one** shared set of instances; for `many_many` they draw from **two different** sets.
- `width` is the scalar relationship attribute `a1` that sets ribbon thickness.
- Optional `pattern` (which of the two patterns this is) and `title`.

## Required data transformation (this is the heart of the renderer)

A chord diagram is driven by a **square N×N matrix**, not by a link list:

1. Build the node set `N` = the **union** of all `source` values and all `target` values. Assign each instance an index `0..N-1`. **Ordering depends on the pattern:**
   - *reflexive* — one entity set; order deterministically (e.g. sorted).
   - *many_many* — two entity sets; order all `source` (`E1`) instances first (sorted), then all `target` (`E2`) instances (sorted), so each group is a **contiguous arc**. Record, per node, which group it belongs to (0 = source set, 1 = target set) for colouring and labelling.
2. Build an `N×N` matrix of zeros. For each row, add its `width` to `matrix[i][j]` where `i = index(source)`, `j = index(target)`.
3. Treat the relationship as **undirected** unless told otherwise: also add the same `width` to `matrix[j][i]` so the chord is symmetric (the connection between A and B is mutual). If several rows share the same unordered pair, sum their widths. (In the bipartite `many_many` case this symmetry simply means ribbons run between the two contiguous groups; no intra-group cells are ever filled.)

## D3 v7 construction

- Inject **two** arrays into the page via `json.dumps`: the ordered `names` array (the instances of `E`) and the `matrix`. The `matrix` must be a **2-D array of arrays** (`[[...],[...],...]`), exactly `N×N` — **do not flatten it to a 1-D array**; `d3.chord()` indexes it as `matrix[i][j]`, so a flat array breaks the layout (NaN angles, nothing renders).
- `d3.chord().padAngle(...).sortSubgroups(d3.descending)` applied to the 2-D `matrix` produces the chord layout.
- Outer **group arcs** (one per instance) via `d3.arc()` with inner/outer radii. Colour by index: for *reflexive*, give each instance its own colour from an ordinal/rainbow scale; for *many_many*, colour by **group** (the two entity sets get two distinct colour families, e.g. a blues ramp for the source set and an oranges ramp for the target set) so the bipartite structure is legible, and add a short legend naming the two entity sets.
- **Ribbons** between instances via `d3.ribbon().radius(innerRadius)`.
- Place a rotated text **label** at each group's mean angle showing the instance name. A chord group object exposes only its `index`, so resolve the name via the injected array: `names[d.index]` (the group's `.data` field is the numeric row sum, **not** the name). Flip text on the left half so it stays upright.
- Centre the diagram in the SVG with a `translate(width/2, height/2)`; leave margin for labels.

## Pitfalls to respect

- The node set is always the **union** of source and target. For *reflexive* the two sides overlap (often identical); for *many_many* they are disjoint but still placed on one circle (as two contiguous, separately-coloured arcs). Do not assume target values are a subset of source values or vice versa.
- The matrix must be exactly square and the same index map must be used for rows, columns, arcs, ribbons, and labels — including the source-then-target ordering in the bipartite case.
- Readability degrades when `N` is large (a chord with ~150 instances is dense). Still render every instance and ribbon faithfully — a smaller, readable diagram is obtained by passing a **filtered data file** at run time (e.g. one region's borders), not by dropping data inside the renderer.
- This is `d3.chord`/`d3.ribbon` (the geometry layout), not `d3-chord` legacy APIs; no removed v5 calls.
