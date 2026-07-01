# Chart-specific instructions: Line chart (weak_entity)

## Pattern context

This renderer serves the `weak_entity` pattern: a weak entity has a compound key made of a parent key `k1` (the foreign-key part of the primary key) and a local child key `k2`, plus a scalar attribute `a1`. The visualisation is a **line chart**: each distinct value of the parent key `k1` is a separate line; the child key `k2` is a scalar dimension on the x-axis and the scalar attribute `a1` is on the y-axis.

## Mapping fields

The mapping names a table and the columns, by **role** — fill them from the actual selection; the
values below are placeholders, not fixed names. This renderer must work for **any** weak-entity
selection whose child key is scalar, not one specific table:

```json
{ "table": "<weak-entity table>", "series": "<parent key k1>", "x": "<scalar child key k2>", "y": "<scalar attribute a1>" }
```

Never hard-code these names; always read them from the mapping at run time.

- `series` (`k1`) — one line per distinct value.
- `x` (`k2`) — the scalar child key on the x-axis (numeric; line charts require k2 scalar).
- `y` (`a1`) — the scalar measure on the y-axis.
- Optional `title`.

## Required data transformation

Group rows by `series`; within each series collect `(x, y)` points. Drop rows whose `x` or `y` is non-numeric; sort each series' points by `x`. Do not aggregate across series.

## D3 v7 construction

- `d3.scaleLinear()` on both axes over the full `x` / `y` extents (`.nice()`), with axis titles.
- One `<path>` per series via `d3.line().x(d=>x(d.x)).y(d=>y(d.y))`, coloured by series (ordinal); with many series use a low stroke-opacity so the bundle is readable.

## Interaction (per the base contract)

Hover a line → raise it and highlight it (full opacity) while dimming the others, and show a tooltip with the series name; restore on mouse-out. This is how a single parent's trajectory is traced out of a dense bundle.

## Pitfalls to respect

- Line charts require a **scalar** child key `k2` (x-axis); if `k2` is discrete this chart is not applicable.
- One line per `series`; do not merge series.
- Use only D3 v7 APIs — no `d3.nest` / `d3.event` removed in v6+.
