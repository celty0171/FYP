# viz_codegen_wordcloud — Step 3 deterministic renderer (basic_entity → word cloud, D3 v7)

The lexical chart of the `basic_entity` row. Layered prompt (`base_d3v7.md` + `chart_wordcloud.md`).
A **special** cell: it needs the official d3-cloud layout plugin, loaded from a CDN at run time.

## Inputs

- `mapping_country.json` — `{table: country, text: name, size: population}` (`text` = the lexical
  key; the country name reads better as a word than the code).
- Data: `mondial_database/mondial_data.json` → `data["tables"]["country"]` (246 words).

## Renderer

`render_wordcloud_reference.py` — D3 v7 + `d3-cloud@1` (CDN), std-lib only, HTML by plain
concatenation. Builds `[{text, value}]` from the rows (drops non-numeric/negative `size`); font size
via `d3.scaleSqrt` (area-proportional) into `[10, 64]`; runs `d3.layout.cloud()` and draws the words
in its **asynchronous** `on("end")` callback; ordinal colour; hover a word → tooltip (word, value) +
dim the rest.

## Validation (structural — layout/pixels need a browser with CDN access)

246 words; `d3-cloud` loaded; `d3.layout.cloud()` used; asynchronous `on("end")` draw; `scaleSqrt`
font sizing; interaction; complete HTML; no forbidden APIs; no f-string. (Words that do not fit the
canvas are dropped by the layout — expected behaviour.)

## Reproduce

```bash
cd experiments
python3 results/viz_codegen_wordcloud/render_wordcloud_reference.py \
  --mapping results/viz_codegen_wordcloud/mapping_country.json \
  --data mondial_database/mondial_data.json \
  --out results/viz_codegen_wordcloud/country_reference.html
```

## Status

Both special basic-entity cells (choropleth, word cloud) are now built and wired into the
`web_pipeline`. Step 2 flags both as *conditional* (a geographical/lexical character cannot be proved
from a SQL type), so the UI surfaces them as clickable "(if geo/lexical)" pills rather than
auto-selecting them.
