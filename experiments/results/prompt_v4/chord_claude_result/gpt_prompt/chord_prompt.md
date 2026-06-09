You are implementing a visualisation from an already selected schema-pattern mapping.

Target library: <LIBRARY>   (e.g. D3.js / Google Charts / Vega)

Task: The selected visualisation is a chord diagram.

Mapping:

* source = <SOURCE_FIELD>
* target = <TARGET_FIELD>
* weight = <WEIGHT_FIELD>

Data: <DATA_FILE>

Additional instruction: <INSTRUCTION>

## Core Requirements

1. Generate one complete runnable HTML file.
2. Use only the target library and its required official dependencies.
3. Keep all data inline in the HTML.
4. Preserve the selected chord mapping exactly:

   * source node = the selected source/key field
   * target node = the selected target/key field
   * chord width/weight = the selected scalar relationship attribute
5. Do not invent fields, aggregate away selected relationships, or change the meaning of the relationship weight.
6. If an optional data filter is provided, apply it before rendering and use only the filtered rows.
7. Include readable labels, dimensions, margins, a short title, and tooltips for exact values.
8. Return code only.

---

## Layout Goal

Minimise visual clutter.

For chord diagrams, clutter is primarily caused by:

* excessive chord crossings inside the circle
* strongly connected groups being placed far apart
* thick chords obscuring weaker relationships
* visually unstable node ordering

The objective is NOT to minimise arc length around the circle.

The objective is:

1. minimise chord crossings through node ordering
2. place strongly related groups adjacent to each other
3. make unavoidable crossings readable
4. preserve relationship semantics exactly

IMPORTANT:

Unlike Sankey diagrams, chord diagrams use a circular layout.

There is no concept of source-column ordering or target-column ordering.

Instead, visual quality is determined mainly by the circular ordering of nodes around the perimeter.

---

## Step A — Build Relationship Structure

1. Build all relationships from the selected source, target and weight fields.

2. Construct a weighted node-node relationship matrix.

For every node pair (A,B), accumulate:

```
weight(A,B)
```

using the selected weight field.

If the data are directed, preserve directionality internally.

Do not symmetrise unless the selected visualisation specification explicitly requires an undirected chord diagram.

3. Compute total relationship weight for every node:

   total_weight(node)

This will be used only for ordering and visual layout.

---

## Step B — Optimise Circular Node Ordering

4. Construct a node affinity matrix.

For every pair of nodes (N_i, N_j), compute how strongly they are related.

Suitable measures include:

* direct relationship weight
* bidirectional relationship weight
* shared-neighbour similarity
* weighted combinations of the above

The goal is to identify which nodes should be adjacent on the circle.

5. Order nodes around the circle so that highly related nodes become adjacent.

Use a deterministic seriation heuristic such as:

* spectral ordering (Fiedler vector)
* greedy nearest-neighbour chaining
* barycentric refinement
* repeated adjacency optimisation

6. Break ties by:

* descending total relationship weight
* then node label

7. Assign each node a circular rank.

The circular rank determines the final clockwise order of arcs.

8. Optionally perform a small fixed number of refinement passes.

A refinement pass may:

* estimate crossing count
* swap adjacent nodes
* accept only changes that reduce crossings

The algorithm must remain deterministic.

---

## Step C — Order Chords Consistently

9. For each node, sort its incident relationships according to the circular rank of the opposite endpoint.

10. Ensure chord placement is consistent with node ordering.

11. Avoid arbitrary relationship ordering that increases local crossings.

12. If the library supports explicit chord sorting, use:

* neighbour rank
* then descending weight

---

## Visual Design Requirements

1. Use sufficient canvas size for the number of nodes.

Large relationship sets should not be compressed into a small circle.

2. Leave adequate inner radius so chords remain distinguishable.

3. Use clear outer arcs for node groups.

4. Colour chords consistently.

Preferred order:

* colour by target group (directed data)
* otherwise colour by source group
* otherwise colour by node identity

5. Use partial chord opacity.

Dense bundles should remain readable.

6. Handle minor relationships explicitly.

Draw chords in ascending weight order so that small relationships are not completely hidden beneath large ones.

Alternatively, give minor relationships slightly higher contrast.

7. Keep labels readable.

For large node counts:

* reduce font size moderately
* avoid label overlap
* truncate only visually
* always expose full labels in tooltips

8. Place labels outside the outer arc whenever possible.

9. Add hover highlighting.

When hovering a node:

* fade unrelated chords
* highlight connected chords
* allow all relationships associated with that node to be traced clearly

10. Add a subtitle explaining what chord width represents.

11. Add tooltips showing:

* source
* target
* exact weight

12. If directionality exists:

* preserve it visually if supported
* otherwise explain in a subtitle or tooltip that the underlying data are directed

---

## Library-Specific Guidance

### D3 Chord Diagram

1. Use D3's official chord layout:

   d3.chord()

2. Explicitly configure:

* padAngle
* sortGroups
* sortSubgroups
* sortChords

3. Drive group ordering using the circular rank computed in Step B.

4. Drive subgroup ordering using neighbour ranks from Step C.

5. Use:

   d3.arc()

for outer groups.

6. Use:

   d3.ribbon()

for chords.

7. Apply hover highlighting to both groups and ribbons.

8. Draw ribbons after arcs and in ascending weight order.

---

### Google Charts Chord Diagram

Google Charts does not provide a native chord diagram.

If Google Charts is the requested target library:

* return an explanatory HTML comment
* implement the closest faithful alternative only if source-target-weight semantics are preserved

Do not silently substitute an unrelated chart type.

---

### Vega

1. Build the relationship matrix explicitly.

2. Compute node ordering before rendering.

3. Use the computed circular ranks to determine arc positions.

4. Render arcs and ribbons separately.

5. Ensure chord ordering follows Step B and Step C.

---

### Vega-Lite

Vega-Lite does not provide native chord diagram support.

Return an HTML comment explaining this limitation.

Only implement a custom Vega-based solution if relationship semantics can be preserved exactly.

---

## Output

Return the complete runnable HTML code only.
