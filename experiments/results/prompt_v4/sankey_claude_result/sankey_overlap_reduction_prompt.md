You are implementing a visualisation from an already selected schema-pattern mapping.
Target library: <LIBRARY>   (e.g. D3.js / Google Charts / Vega)
Task: The selected visualisation is a sankey diagram.
Mapping:
* source = <SOURCE_FIELD>
* target = <TARGET_FIELD>
* weight = <WEIGHT_FIELD>
Data: <DATA_FILE>

## Core Requirements
1. Generate one complete runnable HTML file.
2. Use only the target library and its required official dependencies.
3. Keep all data inline in the HTML.
4. Preserve the selected Sankey mapping exactly:
   - source node = the selected source/key field
   - target node = the selected target/key field
   - link width/weight = the selected scalar relationship attribute
5. Do not invent fields, aggregate away selected relationships, or change the meaning of the link weight.
6. If an optional data filter is provided, apply it before rendering and use only the filtered rows.
7. Include readable labels, dimensions, margins, a short title, and tooltips for exact values.
8. Return code only.

## Layout Goal
Minimise visual clutter. The clutter that matters is the NUMBER OF LINK CROSSINGS, not
the length of any individual link. Optimise crossing count, not link length.

IMPORTANT framing — do not over-promise to yourself:
- In a 1-D (single-column-order) Sankey, some crossings are TOPOLOGICALLY UNAVOIDABLE.
  Any node whose weight is concentrated in one target group but which also has a smaller
  link to a NON-ADJACENT target group will produce a crossing that NO 1-D ordering can remove.
- Therefore the goal is NOT "zero overlap". The goal is: (a) minimise total crossings via
  ordering, then (b) make the unavoidable residual crossings as readable as possible via
  rendering. Never sacrifice global order to hide one unavoidable link.

Apply this ordering strategy before drawing. It is data-agnostic and must scale to any
dataset (many nodes, many target groups, and the common case where MOST sources are
multi-target):

### Step A — Order the target groups by adjacency, not by weight
1. Build all links from the source, target, and weight fields.
2. Compute total incoming weight per target and total outgoing weight per source.
3. Build a target–target affinity matrix: for every pair of targets (T_i, T_j), sum over all
   sources that link to BOTH the quantity min(w_to_Ti, w_to_Tj) (or the product of shares).
   This measures how strongly two target groups "share" sources.
4. Order the target groups along the axis so that high-affinity targets are ADJACENT.
   Use a 1-D seriation heuristic on the affinity matrix (e.g. spectral ordering by the
   Fiedler vector, or greedy nearest-neighbour chaining, or repeated barycentre relaxation).
   Break ties by descending total incoming weight, then by label.
   Rationale: if two groups share many multi-target sources, placing them next to each other
   turns long cross-group links into short hops, which is what actually removes crossings.
5. Assign each target a numeric target rank from top to bottom (after seriation).

### Step B — Order the sources by weighted barycentre (cluster, do not force boundaries)
6. For each source compute the weighted target barycentre:
     source_barycentre = sum(link_weight * target_rank) / sum(link_weight)
7. Sort source nodes by:
   - weighted target barycentre (this clusters sources flowing to the same target)
   - then descending total outgoing weight
   - then source label
   Do NOT force multi-target sources to group boundaries. With target groups already
   seriated by affinity (Step A), the barycentre alone places multi-target sources between
   the groups that matter, and forcing boundary placement would corrupt within-group order
   on datasets where multi-target sources are common. Let the barycentre do the work.
8. Optionally refine iteratively: recompute target rank as the weighted average of incoming
   source ranks, re-seriate only if it reduces estimated crossings, and recompute barycentres.
   Stop after a fixed small number of passes (deterministic).

### Step C — Order links consistently
9. Sort links within each source by target rank.
10. Sort links within each target by source rank.

## Visual Design Requirements
1. Use enough vertical height for the number of source nodes. Do not compress a large
   Sankey into a short canvas.
2. Use generous node padding so adjacent links are separable.
3. Use moderate node width.
4. Colour links by target group (or another consistent group-based scheme) so overlapping
   links remain distinguishable.
5. Use partial link opacity. Dense bundles must be readable without becoming heavy.
6. Treat the unavoidable residual cross-group links explicitly:
   - Draw links in ascending weight order (small/minor links on top) OR give minor links
     (those whose share of their source is below a threshold, e.g. < 25%) slightly higher
     contrast so a thin secondary link is not buried under a thick bundle.
   - Do NOT attempt to hide these links by reordering nodes.
7. Keep node labels readable. With many nodes, use smaller labels, truncate only visually,
   and show the full label in a tooltip.
8. Place labels so they do not sit on top of dense link bundles.
9. Add hover highlighting: on hovering a node, fade all links not connected to it, so any
   single source's links (including its unavoidable cross-group link) can be traced. This is
   the primary mitigation for residual crossings — make them traceable rather than invisible.
10. Add a subtitle explaining what link width represents.

## Library-Specific Guidance
### D3 Sankey
1. Use `d3-sankey`. Load d3 core and d3-sankey as ES modules (`/+esm`) so the d3-sankey
   bundle cannot overwrite the global `d3` object.
2. Explicitly set `nodeId`, `nodeWidth`, `nodePadding`, `extent`, and enough `iterations`.
   If `nodeId` returns `d.name`, link `source`/`target` MUST be the name strings, not indices.
3. Use `nodeAlign(d3.sankeyLeft)` for bipartite many-to-many data.
4. Precompute each node's `order` via Steps A–C and drive `nodeSort` with it; set `linkSort`
   to honour target rank within a source and source rank within a target.
5. Use `d3.sankeyLinkHorizontal()` for link paths.
### Google Charts Sankey
1. Sort input rows by the Step A–C order before `data.addRows`.
2. Use a tall chart, set node width / padding / label font, target-aware colours.
3. Add an HTML comment: Google Charts exposes limited direct control over Sankey routing and
   node order, so only row pre-sorting is available.
### Vega / Vega-Lite
1. Vega-Lite has no native Sankey support — state this in an HTML comment; implement a
   faithful alternative only if it preserves source/target/weight semantics.
2. In Vega, implement the Step A–C ordering and explicit link path control where possible.

## Output
Return the complete runnable HTML code only.
