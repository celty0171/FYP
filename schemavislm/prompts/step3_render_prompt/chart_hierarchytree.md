# Chart-specific instructions: Hierarchy tree (one_many_relationship)

## Pattern context

This renderer serves the `one_many_relationship` pattern: a parent entity `Ep` is connected to a child entity `Ec`, and instances of `Ep` organise or contain instances of `Ec`. The visualisation is a **node-link hierarchy tree**: each instance of the parent `Ep` is a node, connected by lines to its child instances `Ec`. Per the paper this chart is **not** an area chart — unlike the tree map and circle packing it does **not** require a scalar measure (`Hierarchy tree does not require scalar size`). A discrete attribute may **optionally** be used to colour the **links** between the entities (not the nodes).

## Mapping fields

The mapping names a table and the columns, by **role** — fill them from the actual selection; the
values below are placeholders, not fixed names. This renderer must work for **any** one-many
selection, not one specific table:

```json
{ "table": "<child table Ec>", "parent": "<parent key kp = the FK column>", "child": "<child key kc>", "color": "<optional discrete attribute on Ec>" }
```

Never hard-code these names; always read them from the mapping at run time.

- `parent` (`kp`) — the foreign-key column; its distinct values are the parent nodes.
- `child` (`kc`) — the child key; each row is a child node under its parent.
- `color` — **optional** discrete attribute; when present it colours the parent→child links.
- Optional `title`.

## Required data transformation

Build a two-level hierarchy: a synthetic root → one node per distinct `parent` value → one leaf per child row. Drop rows whose `parent` is null/empty. **Do not require or read a scalar measure** — this chart has no size encoding. If `color` is given, carry each child's discrete value so the link to it can be coloured.

## D3 v7 construction

- `d3.hierarchy(data)` then `d3.tree().nodeSize([dx, dy])` for a tidy node-link layout (a horizontal tree reads well: map `x`→vertical, `y`→depth). Size the SVG from the laid-out extent so every node fits; do not impose an arbitrary node cap (the paper sets no completeness/size limit for this chart).
- Draw links with `d3.linkHorizontal()`; draw a circle + label per node. Colour each link by its **target child's** discrete attribute via an ordinal scale when `color` is set, otherwise a neutral grey. Show a legend only when `color` is present.

## Interaction (per the base contract)

Hover a node → tooltip; emphasise the connected links (a parent's links to its children, or a leaf's link to its parent) and de-emphasise the rest; restore on mouse-out. A parent tooltip shows its child count; a leaf tooltip shows its parent (and the colour attribute value, if any).

## Pitfalls to respect

- This is a **node-link** tree, not an area chart — never size nodes by a measure; the chart needs no scalar attribute at all.
- The optional discrete attribute colours the **links**, not the node fills.
- Synthesise a single root so a `d3.hierarchy` exists even with many parents; do not assume one parent.
- Use only D3 v7 APIs — no `d3.nest` / `d3.event` removed in v6+.
