# Chart-specific instructions: Spider / radar chart (weak_entity)

## Pattern context

This renderer serves the `weak_entity` pattern: a weak entity has a compound key made of a parent key `k1` and a local child key `k2`, plus a scalar attribute `a1`. The visualisation is a **spider (radar) chart**: each ring (polygon) is a value of the parent key `k1`, each spoke (axis) is a value of the child key `k2`, and the ring/spoke intersection is the scalar attribute `a1`. It is meaningful only when `a1` is comparable across `k2` for each `k1`, and works best with a **small, complete** weak entity (`|k1|` roughly 3–10, the same `k2` set across rings).

## Mapping fields

The mapping names a table and the columns, by **role** — fill them from the actual selection; the
values below are placeholders, not fixed names. This renderer must work for **any** weak-entity
selection, not one specific table:

```json
{ "table": "<weak-entity table>", "ring": "<parent key k1>", "spoke": "<child key k2>", "value": "<scalar attribute a1>" }
```

Never hard-code these names; always read them from the mapping at run time.

- `ring` (`k1`) — one polygon per distinct value.
- `spoke` (`k2`) — the child key; each distinct value is an axis around the circle.
- `value` (`a1`) — the scalar measure at each ring/spoke intersection.
- Optional `title`. Optional `max_rings` / `max_spokes` to cap a large selection.

## Required data transformation

Build a per-ring map `ring -> { spoke: value }` (sum duplicates). Because a spider is unreadable with many rings/spokes, keep the **top `max_rings`** rings by total value (default ~8) and the **top `max_spokes`** spokes by frequency across those rings (default ~12); pad missing `(ring, spoke)` with 0. State any capping in the subtitle. This realises the chart's completeness requirement rather than dropping data arbitrarily.

## D3 v7 construction

- Place the spokes evenly around a circle (`angle = i / nSpokes · 2π`); a radial `d3.scaleLinear()` from 0 to the max value sets the radius. Draw faint grid rings and a labelled axis per spoke.
- One closed `<path>` (polygon) per ring over the spoke points, with a translucent fill and a coloured stroke (ordinal by ring).

## Interaction (per the base contract)

Hover a ring (polygon or its legend entry) → raise and fully highlight it while dimming the others, and show a tooltip with the ring name; restore on mouse-out.

## Pitfalls to respect

- A spider needs the same `spoke` set across rings to be comparable — pad missing values with 0 and cap to a readable subset.
- `value` must be numeric.
- Use only D3 v7 APIs — no `d3.nest` / `d3.event` removed in v6+.
