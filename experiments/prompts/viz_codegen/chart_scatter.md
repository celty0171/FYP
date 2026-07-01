# Chart-specific instructions: Scatter diagram (basic_entity)

## Pattern context

This renderer serves the `basic_entity` pattern: instances of one entity `E` are identified by a key `k` and described by scalar attributes. The visualisation is a **scatter diagram**: each instance of `E` is a point positioned by two scalar attributes — `a1` on the x-axis and `a2` on the y-axis. An optional third attribute `a3` may colour the points.

## Mapping fields

The mapping names a table and the columns, by **role** — fill them from the actual selection; the
values below are placeholders, not fixed names. This renderer must work for **any** basic-entity
selection with two scalar attributes, not one specific table:

```json
{ "table": "<entity table>", "key": "<entity key column>", "x": "<scalar attribute a1>", "y": "<scalar attribute a2>", "color": "<optional attribute a3>" }
```

Never hard-code these names; always read them from the mapping at run time.

- `key` (`k`) identifies each instance (used in the tooltip).
- `x` (`a1`) and `y` (`a2`) are the two **scalar** attributes giving each point's coordinates (numeric).
- `color` (`a3`) is **optional** — when present, colour points by it (ordinal for a discrete attribute).
- Optional `title`.

## Required data transformation

One point **per entity instance**: `{label: key, x: a1, y: a2, color?: a3}`. Drop rows whose `x` or `y` is non-numeric. Do not aggregate — each instance of `E` is its own point.

## D3 v7 construction

- `d3.scaleLinear()` for both axes (`d3.extent(...).nice()`); x-axis bottom, y-axis left, each with an axis title naming its column.
- One `<circle>` per instance at `(x(d.x), y(d.y))` with a small fixed radius; if `color` is mapped, use `d3.scaleOrdinal(..., d3.schemeCategory10)`; otherwise a single fill.
- Use partial fill-opacity so overlapping points remain visible.

## Interaction (per the base contract)

Hover a point → tooltip showing the key and the mapped attribute values, and emphasise that point while dimming the rest; restore on mouse-out.

## Pitfalls to respect

- One point per entity instance — do not aggregate.
- `x` and `y` must be numeric; drop rows missing either.
- `color` is optional; only build a colour scale when it is mapped.
- Use only D3 v7 APIs — no `d3.nest` / `d3.event` removed in v6+.
