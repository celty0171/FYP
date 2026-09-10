# Chart-specific instructions: Stacked bar chart (weak_entity)

## Pattern context

This renderer serves the `weak_entity` pattern: a weak entity has a compound key made of a parent key `k1` and a local child key `k2`, plus a scalar attribute `a1`. The visualisation is a **stacked bar chart**: each distinct value of the parent key `k1` is a bar; each stacked segment of that bar is a value of the child key `k2`; the scalar attribute `a1` sets the segment length. It assumes completeness — each `k1` should have the same, or almost the same, set of `k2` values so the stacks are comparable (missing combinations are treated as zero).

## Mapping fields

The mapping names a table and the columns, by **role** — fill them from the actual selection; the
values below are placeholders, not fixed names. This renderer must work for **any** weak-entity
selection, not one specific table:

```json
{ "table": "<weak-entity table>", "group": "<parent key k1>", "segment": "<child key k2>", "value": "<scalar attribute a1>" }
```

Never hard-code these names; always read them from the mapping at run time.

- `group` (`k1`) — one bar per distinct value.
- `segment` (`k2`) — the child key; each distinct value is a stacked segment (a series in the stack).
- `value` (`a1`) — the scalar measure setting each segment's length.
- Optional `title`.

## Required data transformation

Build the set of distinct `group` values (bars) and the distinct `segment` values. For each `(group, segment)` sum `value` (treat a missing combination as 0).

**Enforce completeness (mandatory, per the paper).** A stacked bar is only meaningful when each `k1` bar carries the same, or almost the same, set of `k2` values, so the stacks are comparable. Real weak entities have a long tail of `segment` values that occur for only one or two groups; stacking all of them produces hundreds of unshared, non-comparable segments. So **rank the segments by how many groups they appear in** (coverage; tie-break by total `value`), keep the top `max_segments` shared ones (a sensible default such as 12) as the comparable core, and **fold every remaining segment into a single `(other)` band per group**. Folding the tail (rather than dropping it) preserves each bar's part-to-whole total. State in the subtitle how many segments were kept and how many were folded. Then form a stack with `d3.stack().keys(<kept segments + "(other)">)` over one row per group.

## D3 v7 construction

- A **horizontal** stacked bar chart so many groups stay readable: `d3.scaleBand()` on groups (y), `d3.scaleLinear()` on the cumulative value (x).
- `d3.stack().keys(segments)`; draw one `<rect>` per (group, segment) at `[x(d[0]), x(d[1])]`; colour by segment with an ordinal scale; a measure axis and group labels.

## Interaction (per the base contract)

Hover a segment → tooltip showing the group, the segment, and the value; emphasise the hovered segment (e.g. raise opacity / outline) while dimming the rest; restore on mouse-out.

## Pitfalls to respect

- One bar per `group`; segments are the `segment` values; do not aggregate groups together.
- Fill missing `(kept group, kept segment)` combinations with 0 so stacks are comparable.
- Do **not** emit one stack key per distinct `segment` for a long-tailed weak entity — keep the shared core and fold the rest into `(other)` (see completeness above), or the chart becomes hundreds of unshared bands and a huge file.
- Give `(other)` a neutral colour (e.g. grey) so it reads as the residual, not a real category.
- `value` must be numeric; drop/skip non-numeric rows.
- Use only D3 v7 APIs — no `d3.nest` / `d3.event` removed in v6+.
