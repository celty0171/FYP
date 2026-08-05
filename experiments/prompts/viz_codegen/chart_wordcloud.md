# Chart-specific instructions: Word cloud (basic_entity)

## Pattern context

This renderer serves the `basic_entity` pattern when the entity key is **lexical** (words / labels): instances of one entity `E` are identified by a textual key `k`, and a scalar attribute `a1` sets each word's size. The visualisation is a **word cloud**.

## Mapping fields

The mapping names a table and the columns, by **role** — fill them from the actual selection; the
values below are placeholders, not fixed names. This renderer must work for **any** basic-entity
selection whose key is lexical, not one specific table:

```json
{ "table": "<entity table>", "text": "<lexical key column>", "size": "<scalar attribute>", "color": "<optional attribute a2>", "color_type": "discrete | scalar" }
```

The optional `color` (`a2`, paper Section 3) colours each word via the companion **`color_type`**: `"discrete"` → an **ordinal colour key**; `"scalar"` → a **sequential colour spectrum** over the numeric range. Absent `color` → the default per-word palette (unchanged).

Never hard-code these names; always read them from the mapping at run time.

- `text` (`k`) — the word for each instance (the lexical key).
- `size` (`a1`) — the scalar attribute that sets the word's font size (numeric, `>= 0`).
- Optional `title`.

## External dependency (layout plugin)

A word cloud needs the official **d3-cloud** layout plugin, loaded from a CDN inside the produced HTML (in addition to D3 v7):

```html
<script src="https://cdn.jsdelivr.net/npm/d3-cloud@1/build/d3.layout.cloud.js"></script>
```

(it attaches `d3.layout.cloud`).

## Required data transformation

Build `[{text, value}]` from the rows, dropping non-numeric `size`. Map `value` to a font size with a **`d3.scaleSqrt`** (area-proportional) into a sensible pixel range (e.g. `[10, 64]`).

## D3 v7 construction

- `d3.layout.cloud().size([w, h]).words(words).padding(2).rotate(0).font("Arial").fontSize(d => d.size).on("end", draw)` then `.start()`.
- In `draw`, append one `<text>` per laid-out word at `(d.x, d.y)` with `font-size: d.size`. Colour: if `color` is mapped, branch on `color_type` (discrete → ordinal key; scalar → sequential spectrum); otherwise a default ordinal palette. The layout is **asynchronous** (positions are computed then `on("end")` fires) — draw inside the callback. Words that do not fit are dropped by the layout; that is expected.

## Interaction (per the base contract)

Hover a word → tooltip showing the word and its value, and emphasise it (e.g. raise opacity / bold) while dimming the rest; restore on mouse-out.

## Pitfalls to respect

- Size must encode through **area** (`scaleSqrt`), not a linear font size.
- The layout is asynchronous — render in the `on("end")` callback, not synchronously.
- `size` must be numeric; drop non-numeric rows.
- Use only D3 v7 APIs (plus `d3-cloud`) — no `d3.nest` / `d3.event` removed in v6+.
