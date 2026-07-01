# Chart-specific instructions: Bubble chart (basic_entity)

## Pattern context

This renderer serves the `basic_entity` pattern: instances of one entity `E` are identified by a key `k` and described by scalar attributes. The visualisation is a **bubble chart** — a scatter diagram with a third scalar encoded as bubble size: each instance is a bubble positioned by `a1` (x) and `a2` (y), with `a3` setting its **area**. An optional fourth attribute `a4` may colour the bubbles.

## Mapping fields

The mapping names a table and the columns, by **role** — fill them from the actual selection; the
values below are placeholders, not fixed names. This renderer must work for **any** basic-entity
selection with three scalar attributes, not one specific table:

```json
{ "table": "<entity table>", "key": "<entity key column>", "x": "<scalar attribute a1>", "y": "<scalar attribute a2>", "size": "<scalar attribute a3>", "color": "<optional attribute a4>" }
```

Never hard-code these names; always read them from the mapping at run time.

- `key` (`k`) identifies each instance (used in the tooltip).
- `x` (`a1`) and `y` (`a2`) are the scalar coordinates; `size` (`a3`) sets each bubble's **area** (numeric, `>= 0`).
- `color` (`a4`) is **optional** — when present, colour bubbles by it.
- Optional `title`.

## Required data transformation

One bubble **per entity instance**: `{label: key, x: a1, y: a2, size: a3, color?: a4}`. Drop rows whose `x`, `y`, or `size` is non-numeric. Do not aggregate.

## D3 v7 construction

- `d3.scaleLinear()` for both axes (`d3.extent(...).nice()`), each with an axis title naming its column.
- **`d3.scaleSqrt()`** for the radius so bubble **area** (not radius) is proportional to `size` (domain `[0, max size]`, a sensible pixel range, e.g. `[3, 22]`).
- One `<circle>` per instance at `(x(d.x), y(d.y))` with `r = rScale(d.size)`; if `color` is mapped, use an ordinal colour scale; partial fill-opacity so overlapping bubbles stay visible. Draw larger bubbles first (smaller on top) so small bubbles are not hidden.

## Interaction (per the base contract)

Hover a bubble → tooltip showing the key and the mapped attribute values (including `size`), and emphasise that bubble while dimming the rest; restore on mouse-out.

## Pitfalls to respect

- One bubble per entity instance — do not aggregate.
- Encode `size` through **area** via `scaleSqrt`, not a linear radius (a linear radius exaggerates large values).
- `x`, `y`, `size` must be numeric; drop rows missing any of them.
- Use only D3 v7 APIs — no `d3.nest` / `d3.event` removed in v6+.
