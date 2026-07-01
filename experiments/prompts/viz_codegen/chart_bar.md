# Chart-specific instructions: Bar chart (basic_entity)

## Pattern context

This renderer serves the `basic_entity` pattern: instances of one entity `E` are identified by a key `k` and described by scalar attributes. The visualisation is a **bar chart**: each instance of `E` (identified by `k`) is a bar, and a scalar attribute `a1` sets the bar's length.

## Mapping fields

The mapping names a table and the columns, by **role** — fill them from the actual selection; the
values below are placeholders, not fixed names. This renderer must work for **any** basic-entity
selection, not one specific table:

```json
{ "table": "<entity table>", "key": "<entity key column>", "measure": "<scalar attribute>" }
```

Never hard-code these names; always read them from the mapping at run time.

- `key` (`k`) is the entity key identifying each instance — one bar per distinct key.
- `measure` (`a1`) is the scalar attribute that sets bar length (numeric; drop rows whose measure is non-numeric).
- Optional `title`.

## Required data transformation

One bar **per entity instance**: `{label: key, value: measure}`. Drop rows with a non-numeric measure. Sort by measure descending for readability. Do **not** aggregate — each instance of `E` is its own bar.

## D3 v7 construction

- Draw a **horizontal** bar chart so many category labels stay readable: `d3.scaleBand()` on the keys (y-axis) and `d3.scaleLinear()` on the measure (x-axis, `.nice()`).
- One `<rect>` per instance with width = `x(value)`; a category axis with labels (small font) and a measure axis with ticks; value labels at the bar ends when they fit.
- Use enough **height** for the number of bars — do not compress a long bar chart into a short canvas.

## Interaction (per the base contract)

Hover a bar → tooltip showing the key and the measure value, and emphasise that bar while dimming the rest; restore on mouse-out.

## Pitfalls to respect

- One bar per entity instance — do not aggregate away instances.
- The measure must be numeric; drop or skip non-numeric rows rather than coercing them.
- With many instances use a tall canvas and horizontal bars; keep the full label/value in the tooltip even if the on-chart label is small.
- Use only D3 v7 APIs — no `d3.nest` / `d3.event` removed in v6+.
