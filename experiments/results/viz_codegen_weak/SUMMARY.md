# viz_codegen_weak — Step 3 deterministic renderers (weak_entity → line / stacked / grouped / spider, D3 v7)

The `weak_entity` row: four chart blocks (`chart_line.md`, `chart_stacked.md`, `chart_grouped.md`,
`chart_spider.md`) on the shared `base_d3v7.md`, with four renderers in this dir. A weak entity has a
compound key of a parent key `k1` and a local child key `k2` plus a scalar `a1`; all four charts pivot
the rows by `k1 × k2`. Same paradigm: each renderer is written once; data is read at run time and never
enters the prompt.

## Cases and inputs

- **line** — `country_population` (weak: PK `country, year`; `country` FK): `series = country` (k1),
  `x = year` (scalar k2), `y = population` (a1). One line per country over census years.
- **stacked / grouped / spider** — `ethnic_group` (weak: PK `name, country`; `country` FK):
  `k1 = country`, `k2 = name` (ethnic group), `a1 = percentage`. Each country's ethnic composition
  (sums ≈ 100%).
- Data: full `mondial_database/mondial_data.json` selected by `mapping["table"]`. Mappings match the
  Step-2 output shapes exactly (`{series,x,y}`, `{group,segment,value}`, `{ring,spoke,value}`).

## Renderers

- `render_line_reference.py` — group by series; drop non-numeric x/y; sort each series by x; one
  `d3.line` path per series, low stroke-opacity; hover a line → raise + highlight + tooltip (trace one
  country out of the bundle).
- `render_stacked_reference.py` — distinct groups (bars) × segments; `(group, segment)` summed.
  **Enforces the paper's completeness requirement**: ranks segments by coverage (how many groups
  contain them, tie-broken by total), keeps the top `max_segments` (default 12) shared ones as the
  comparable core, and **folds the long tail into one `(other)` band** per bar — preserving each bar's
  part-to-whole total. Missing `(group, kept-segment)` padded to 0; horizontal `d3.stack`; ordinal
  colour with grey `(other)`; legend; hover a segment → highlight + tooltip (group, segment, value).
  The subtitle reports kept-vs-folded counts.
- `render_grouped_reference.py` — the **comparison** sibling of the stacked bar: one cluster per `k1`,
  one bar per `k2` side by side, height = `a1` (`d3.scaleBand` x0 over groups × x1 over segments).
  Same completeness rule, but as a comparison (not a composition) it **drops** the tail instead of
  folding to `(other)`: keeps the top `max_segments` (default 8) segments by coverage and the top
  `max_groups` (default 12) **most-complete** groups (those carrying the most kept segments, tie-broken
  by total). Pads missing `(group, segment)` to 0; ordinal colour; legend; rotated group labels; hover
  a bar → highlight that segment across all clusters + tooltip. Both caps + dropped counts in the
  subtitle.
- `render_spider_reference.py` — per-ring `{spoke: value}`; because a radar is unreadable with many
  rings/spokes, keeps the **top `max_rings`** (default 8) rings by total and **top `max_spokes`**
  (default 12) spokes by frequency, padding missing with 0 (this realises the chart's completeness
  requirement per pattern_notes); radial `scaleLinear`, closed polygons, hover a ring → highlight +
  tooltip. The cap is stated in the subtitle.

All three: D3 v7, std-lib only, HTML by plain concatenation (no f-string / `str.format`), no forbidden
v6+ APIs.

## Validation

| chart | result |
|-------|--------|
| line | 246 series (country_population), `d3.line`, hover, complete HTML |
| stacked | 241 bars; kept 12 shared ethnic groups (European in 66 bars, Arab 51, African 48, …) + folded 484 into `(other)`; bars sum ≈ 100% (part-to-whole preserved); 56 KB; complete |
| grouped | top 12 most-complete countries (USA, China, Trinidad, Suriname, Jamaica, … each carrying 4–5 of the kept segments) × top 8 shared ethnic groups, side by side; dropped tail; 5.5 KB; `scaleBand×scaleBand`, no `d3.stack`; complete |
| spider | rings capped to 8, spokes to 12, radial scale + closed polygons, subtitle notes the cap, complete |

End-to-end through `web_pipeline`: `country_population` → line (56 KB) and `ethnic_group` → stacked
(56 KB, comparable core + `(other)`) both render with `available=True`; grouped and spider render on
demand. All four weak charts that Step 2 recommends now resolve to a renderer — none return
`working in process`.

## Reproduce

```bash
cd experiments
python3 results/viz_codegen_weak/render_line_reference.py    --mapping results/viz_codegen_weak/mapping_line.json    --data mondial_database/mondial_data.json --out results/viz_codegen_weak/line_reference.html
python3 results/viz_codegen_weak/render_stacked_reference.py --mapping results/viz_codegen_weak/mapping_stacked.json --data mondial_database/mondial_data.json --out results/viz_codegen_weak/stacked_reference.html
python3 results/viz_codegen_weak/render_grouped_reference.py --mapping results/viz_codegen_weak/mapping_grouped.json --data mondial_database/mondial_data.json --out results/viz_codegen_weak/grouped_reference.html
python3 results/viz_codegen_weak/render_spider_reference.py  --mapping results/viz_codegen_weak/mapping_spider.json  --data mondial_database/mondial_data.json --out results/viz_codegen_weak/spider_reference.html
```

## Status / next

- The weak row closes the end-to-end loop for cases 5–6 in the pipeline (their *selected* charts now
  render) and all four weak charts Step 2 recommends (line/stacked/grouped/spider) are built. The only
  unbuilt Step-3 cell left in the taxonomy is `one_many → hierarchy tree`.
- The stacked renderer now follows the paper's completeness rule (shared core + `(other)`), so it is
  bounded and comparable regardless of how long the segment tail is. The large `(other)` band for
  `ethnic_group` is the honest signal the paper predicts — ethnic composition has weak completeness
  (most ethnic groups are country-specific) — while the 12 cross-country groups stay comparable bar
  to bar. `max_segments` is overridable in the mapping.
