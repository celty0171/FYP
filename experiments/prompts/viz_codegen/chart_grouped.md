# Chart-specific instructions: Grouped bar chart (weak_entity)

## Pattern context

This renderer serves the `weak_entity` pattern: a weak entity has a compound key made of a parent key `k1` and a local child key `k2`, plus a scalar attribute `a1`. The visualisation is a **grouped (clustered) bar chart**: one cluster per distinct value of the parent key `k1`; within each cluster, one bar per value of the child key `k2` placed side by side; the bar height is the scalar attribute `a1`. It is the **comparison** sibling of the stacked bar — instead of stacking `a1` into a part-to-whole total, it puts the `a1` values next to each other so they can be compared across `k1`. It assumes completeness: each `k1` should carry the same, or almost the same, set of `k2` values, otherwise the side-by-side comparison is not meaningful.

## Mapping fields

The mapping names a table and the columns, by **role** — fill them from the actual selection; the
values below are placeholders, not fixed names. This renderer must work for **any** weak-entity
selection, not one specific table:

```json
{ "table": "<weak-entity table>", "group": "<parent key k1>", "segment": "<child key k2>", "value": "<scalar attribute a1>" }
```

Never hard-code these names; always read them from the mapping at run time.

- `group` (`k1`) — one cluster per distinct value.
- `segment` (`k2`) — the child key; each distinct value is one bar inside every cluster.
- `value` (`a1`) — the scalar measure setting each bar's height.
- Optional `title`; optional `max_groups`, `max_segments` to override the core caps below.

## Required data transformation

Build the distinct `group` values and the distinct `segment` values. For each `(group, segment)` sum `value` (treat a missing combination as 0).

**Enforce completeness (mandatory, per the paper).** A grouped bar is only meaningful when each cluster compares the same set of `k2` bars, and it gets unreadable once there are many groups or many segments. Because this is a **comparison** (not a composition), do **not** fold the tail into an `(other)` bar — a side-by-side sum of unrelated segments would be meaningless. Instead keep only the comparable core: rank `segment` values by **coverage** (how many groups they appear in, tie-broken by total `value`) and keep the top `max_segments` (a small default such as 8); then keep the `group` values best described by those segments (largest summed `value` over the kept segments), up to `max_groups` (a small default such as 12). Pad missing `(kept group, kept segment)` with 0. State both caps — and how many groups/segments were dropped — in the subtitle.

## D3 v7 construction

- Two band scales: `x0 = d3.scaleBand()` over the kept groups across the width; `x1 = d3.scaleBand()` over the kept segments **within** `x0.bandwidth()`. A linear `y` over `[0, max value]`.
- One `<g>` per group translated to `x0(group)`; inside it one `<rect>` per segment at `x1(segment)`, height `innerH - y(value)`; colour by segment with an ordinal scale; a value axis, rotated group labels, and a segment legend.

## Interaction (per the base contract)

Hover a bar → tooltip showing the group, the segment, and the value; emphasise every bar of the hovered segment (same colour across clusters) while dimming the rest; restore on mouse-out.

## Pitfalls to respect

- One cluster per `group`; one bar per `segment`; do not stack — bars sit side by side sharing a baseline.
- Keep the comparable core and drop the long tail (see completeness above); do not emit a bar per distinct `segment` for a long-tailed weak entity, or the chart becomes unreadable.
- Do not fold the tail into `(other)` (that belongs to the stacked/composition chart, not this comparison chart).
- `value` must be numeric; drop/skip non-numeric rows.
- Use only D3 v7 APIs — no `d3.nest` / `d3.event` removed in v6+.
