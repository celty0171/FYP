# web_pipeline — deterministic Step 1 → 2 → 3 front-end

A web UI that wires the three **deterministic** pipeline programs together — **no model calls**. Pick a
Mondial table and columns; the server classifies the ER pattern, recommends charts + a mapping, and
renders the chosen chart, all from the in-repo programs.

## Wiring

| step | program |
|------|---------|
| 1 — ER pattern | `results/prompt_v9_codegen/gpt_generated.py` (`classify_selection`; 9/9 vs baseline) |
| 2 — chart recommendation + mapping | `results/step2_codegen/gpt_recommend_charts.py` (`recommend`) |
| 3 — visualisation | `results/viz_codegen_*/render_*_reference.py` (`render` + `_rows_for`) |
| data | `mondial_database/mondial_data.json` (grouped; the table is selected by `mapping["table"]`) |

Every chart Step 2 can recommend now has a built renderer (15 in total): **bar, scatter, bubble,
calendar, choropleth, word cloud** (basic); **line, stacked, grouped, spider** (weak); **tree map,
circle packing, hierarchy tree** (one-many); **Sankey** and **chord** (both serve **both** the
many-many and reflexive-many-many patterns — each renderer is pattern-aware, so the same two charts
are offered for either relationship). The `working in process` placeholder remains in the server for
any future chart name without a renderer, but no recommended chart hits it today.

## Run

```bash
python experiments/web_pipeline/server.py --port 8090
# then open http://127.0.0.1:8090  (use an SSH tunnel if running on the HPC)
```

## API

- `GET /api/schema` → `{ tables: { <table>: [columns...] } }`.
- `POST /api/run` `{ table, columns }` → `{ step1:{pattern,reason}, step2:{recommended_charts,
  candidates,selected}, step3:{chart,available,html} }`. `step3.html` is a complete standalone HTML
  document when `available`, else the literal `working in process`.
- `POST /api/render` `{ chart, mapping }` → `{ chart, available, html }`. Used by the UI when you click
  a different recommended chart.

## UI

Left: table dropdown + column checkboxes + **Run pipeline**. Right: the identified pattern, the
recommended charts as clickable pills (a ⏳ marks charts not built yet; conditional geo/lexical charts
show as "(if geo/lexical)"), the selected mapping JSON, and the rendered chart in a sandboxed
`<iframe>` (or the `working in process` placeholder).

### Visualisation controls

The Step-3 panel has a toolbar above a large (`72vh`) scrollable viewport. The controls act on the
currently rendered chart:

| control | effect |
|---------|--------|
| **−** / **+** / **Reset** | zoom the chart out / in / back to 100% (`transform: scale`, 25 %–400 %). The viewport scrolls so you can pan a zoomed-in chart; the percentage is shown between the buttons. |
| **⤢ Fullscreen** | expand the panel to fill the window for close inspection; press **Esc** (or the button again) to exit. |
| **Open in tab** | open the chart's standalone HTML in a new browser tab (native zoom / print / save). |
| **Download** | save the chart as a self-contained `<chart-name>.html` file you can open offline. |

The buttons are disabled until a chart is rendered, and zoom resets to 100 % each time you render a new
chart. Download / open-in-tab use the chart's own HTML string (the same standalone document the Step-3
renderers emit), so the file works without the server. The viewport re-fits on window resize.

Standard library only; the rendered HTML loads D3 from its CDN inside the sandboxed iframe.
