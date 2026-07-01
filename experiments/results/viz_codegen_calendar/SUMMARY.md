# viz_codegen_calendar — Step 3 deterministic renderer (basic_entity → calendar, D3 v7)

Eighth Step-3 cell, the date-attribute chart of the `basic_entity` row. Layered prompt
(`base_d3v7.md` + `chart_calendar.md`). Same paradigm: the renderer is written once; data is read at
run time and never enters the prompt.

## Case and inputs

- Pattern `basic_entity`, case 4 (`organization`): the canonical date attribute in Mondial is
  `organization.established` (153 full `YYYY-MM-DD` dates, 1865–2011).
- `mapping_organization.json` — `{table: organization, date: established, key: abbreviation}`.
- Data: full `mondial_database/mondial_data.json` → `data["tables"]["organization"]`.

## Renderer

`render_calendar_reference.py` — D3 v7, std-lib only, HTML by plain concatenation. Construction:

- Parses the `date` column (keeps only valid `YYYY-MM-DD`); buckets instances by ISO day; per-day
  value = **count** of instances (or sum of an optional `measure`); keeps the per-day instance-key
  list for the tooltip.
- One **year strip** per year that has data (weeks × weekday grid), so a sparse 146-year range emits
  64 short strips, **not** hundreds of empty rows.
- Day cells positioned with **UTC** helpers (`d3.utcDays`, `d3.utcSunday.count(d3.utcYear(d), d)`,
  `d.getUTCDay()`) to avoid timezone drift; coloured by value via `d3.scaleSequential(interpolateBlues)`;
  month guides across the top, a year label per strip.
- Hover a day with instances → tooltip (date, value, instance keys) + contrasting cell stroke.

## Validation

| check | result |
|-------|--------|
| days with data | 147 (expected 147) |
| years rendered | 64 (only years with data; range 1865–2011) |
| instances placed | 153 (all valid organisations) |
| spot check | 1964-09-09 → AfDB |
| contract | D3 v7 + UTC helpers, sequential colour, no forbidden APIs, interaction (tooltip + stroke), no f-string, complete HTML |

## Reproduce

```bash
cd experiments
python3 results/viz_codegen_calendar/render_calendar_reference.py \
  --mapping results/viz_codegen_calendar/mapping_organization.json \
  --data mondial_database/mondial_data.json \
  --out results/viz_codegen_calendar/organization_reference.html
```

## Status / next

Calendar done — the `basic_entity` row now covers bar, scatter, bubble, calendar. Remaining basic
charts both need extra dependencies and are special cells:

- **choropleth** — external TopoJSON/GeoJSON country geometry (breaks the relational-rows contract).
- **word cloud** — the d3-cloud plugin CDN.

Then the `weak` row: line / stacked bar / spider. Qwen/Coder runs deferred until Coder-32B (8004).
