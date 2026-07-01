# Chart-specific instructions: Circle packing (one_many_relationship)

## Pattern context

This renderer serves the `one_many_relationship` pattern: a parent entity `Ep` organises or contains instances of a child entity `Ec`; the selected child table carries a foreign key to the parent that is **not** part of its primary key. The visualisation is **circle packing**: each parent instance is a circle that contains a circle for each of its child instances, and a scalar child attribute sets each child circle's area.

## Mapping fields

The mapping names a table and three columns, by **role** — fill them from the actual selection; the
values below are placeholders, not fixed names. This renderer must work for **any** one-many
selection, not one specific table:

```json
{ "table": "<child table>", "parent": "<parent FK column on the child table>", "child": "<child key column>", "measure": "<scalar child attribute>" }
```

Never hard-code these names; always read them from the mapping at run time.

- `parent` (`kp`) is the foreign-key column on the child table that references the parent `Ep`. Child rows whose `parent` value is null/missing are **not** part of the relationship and must be excluded.
- `child` (`kc`) is the child instance key (`Ec`).
- `measure` (`a1`) is a scalar child attribute that sets each child circle's area; it must be `>= 0` (floor missing/negative/non-numeric values to 0 or drop them).
- Optional `title`.

## Required data transformation

Build a **two-level hierarchy**: a synthetic root → one node per distinct `parent` value → one leaf per child row, with the leaf value = `measure`. Drop child rows with a null `parent` or a non-numeric `measure`. Group the children under their parent so each parent is one subtree. (This is the same hierarchy a tree map uses; only the layout differs.)

## D3 v7 construction

- `d3.hierarchy(rootObject).sum(d => d.value || 0).sort((a, b) => b.value - a.value)`.
- `d3.pack().size([innerW, innerH]).padding(3)` applied to the root, which assigns `x`, `y`, `r` to every node.
- One `<circle>` per node: draw the parent circles (depth 1) as containers and the child circles (leaves) inside them; **colour leaves by their parent** so each parent's children share a hue. Add parent labels near each parent circle, child labels only when the circle is large enough to fit text, and full detail in a tooltip.
- `d3.hierarchy` / `d3.pack` are in the D3 v7 bundle — no extra plugin.

## Interaction (per the base contract)

Hover a child circle → tooltip showing the child, its parent, and the measure value, and emphasise the hovered child's siblings (same parent) while dimming the rest; restore on mouse-out.

## Pitfalls to respect

- **Exclude children with no parent** (null foreign key) — they are not in the one_many selection; do not bucket them under a fake parent.
- The measure drives area, so it must be non-negative; floor missing/`<= 0` values rather than passing negatives to the layout.
- A parent with a single child is valid (one circle inside its parent circle).
- Use only D3 v7 APIs — no `d3.nest` / `d3.event` removed in v6+.
