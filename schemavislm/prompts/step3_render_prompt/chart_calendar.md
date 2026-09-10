# Chart-specific instructions: Calendar chart (basic_entity)

## Pattern context

This renderer serves the `basic_entity` pattern: instances of one entity `E` are identified by a key `k` and described by attributes. The visualisation is a **calendar chart**: each instance of `E` is placed on a calendar by a date-valued attribute `a1`. Each day cell is coloured by the day's value — by default the **count** of instances that fall on that day, or, when an optional scalar `a2` is mapped, the sum/aggregate of that measure.

## Mapping fields

The mapping names a table and the columns, by **role** — fill them from the actual selection; the
values below are placeholders, not fixed names. This renderer must work for **any** basic-entity
selection with a date attribute, not one specific table:

```json
{ "table": "<entity table>", "date": "<date attribute a1>", "key": "<entity key column>", "measure": "<optional scalar a2>" }
```

Never hard-code these names; always read them from the mapping at run time.

- `date` (`a1`) is the date-valued attribute (`YYYY-MM-DD`) that places each instance.
- `key` (`k`) identifies each instance (listed in the tooltip).
- `measure` (`a2`) is **optional** — when present, a day's value is the sum of `measure` over the instances on that day; when absent, a day's value is the **count** of instances on that day.
- Optional `title`.

## Required data transformation

Parse the `date` column; keep only rows with a valid `YYYY-MM-DD` date. Bucket instances by ISO day; per-day value = count (or sum of `measure`). Keep the per-day list of instance keys for the tooltip. Determine the set of **years that have data**.

## D3 v7 construction

- One horizontal **year strip** per year that has data (stacked vertically), each a grid of weeks (x) × weekday (y, 0–6). Render only years present in the data — a sparse multi-decade range should not emit hundreds of empty year rows.
- One `<rect>` per day at `x = weekOfYear(d) · cell`, `y = weekday(d) · cell` (use `d3.utcSunday.count(d3.utcYear(d), d)` for the week index and `d.getUTCDay()` for the weekday). Use UTC date helpers (`d3.utcDays`, `d3.utcFormat`) to avoid timezone drift.
- Colour days with a value via a **sequential** scale (`d3.scaleSequential(d3.interpolateBlues).domain([0, maxValue])`); leave empty days a neutral grey. Add a year label at the left of each strip and month guides across the top.

## Interaction (per the base contract)

Hover a day that has instances → tooltip showing the date, the day's value, and the list of instance keys; emphasise the hovered cell (e.g. a contrasting stroke); restore on mouse-out.

## Pitfalls to respect

- Keep only rows with a parseable `YYYY-MM-DD` date; skip nulls/partial dates.
- Use **UTC** date helpers throughout so a day does not shift by a timezone offset.
- Default a day's value to the **count** of instances when no `measure` is mapped.
- Render only years that have data; do not emit empty year rows for a wide, sparse range.
- Use only D3 v7 APIs — no `d3.nest` / `d3.event` removed in v6+.
