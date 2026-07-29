You are an expert in schema-driven data visualisation and front-end code generation, working on the Mondial visualisation project.

Your task is not to draw one chart for one dataset. Your task is to write a deterministic Python program that renders a visualisation for any selection of the relevant schema pattern, given a chart mapping and the data rows at run time. The model is used once to author the renderer; thereafter rendering is reproducible code. The data is supplied to the program as a file at run time — it is not embedded in this prompt, and your program must not assume any particular dataset, value set, or row count.

# A. Renderer contract (shared by every chart)

Write a single self-contained Python module, standard library only, deterministic (no randomness, no network calls at generation time, and no run-time network beyond the pinned D3 CDNs inside the produced HTML). It must:

- Expose a function `render(mapping: dict, rows: list[dict]) -> str` that returns the complete HTML document as a string.
- Provide a CLI `--mapping <file> --data <file> --out <file>` that loads the mapping JSON and the data JSON array, calls `render`, and writes the HTML to `--out`.
- Run as-is under `python3 <module>.py --mapping ... --data ... --out ...` and produce a browser-openable file regardless of how many rows the data has.
- Import only the few standard-library modules you actually use (e.g. `argparse`, `json`, `html`, `pathlib`). Do not emit long speculative import lists.
- Do not assemble the HTML with any brace-based templating — no Python f-strings and no `str.format()` / `str.format_map()`. The embedded JavaScript contains literal `{ … }` blocks (arrow-function bodies, object literals) and `${ … }` template literals; an f-string treats them as expressions (`SyntaxError`) and `.format()` treats them as field names (`KeyError`). The only allowed ways to inject the JSON are: (a) plain string concatenation, e.g. `"... const names = " + names_json + "; ..."`, or (b) `str.replace` on non-brace placeholder tokens, e.g. a plain triple-quoted template containing `__NAMES__` / `__MATRIX__` and then `template.replace("__NAMES__", names_json).replace("__MATRIX__", matrix_json)`. Keep all JavaScript braces in the template exactly as written — never escape or double them.

The mapping is a JSON object describing the schema-to-chart encoding. It always carries the column-name fields named in the chart-specific section below (e.g. `source`/`target`/`width`), and may carry an optional `"title"`. These are the names of columns in the data rows — always read the column names from the mapping, never hard-code Mondial column names like `country`/`continent`/`length`. The program may also accept a full Stage-1/2 result object and read the encoding from its `chart_mapping` (or `selected_visualisation.encoding`) field, but reading the bare mapping fields is sufficient.

The data file is **either** a JSON array of row objects, **or** the full grouped Mondial database of the form `{"tables": {"<table>": [ {row}, ... ], ...}}` (e.g. `mondial_data.json`). When it is the grouped form, select the relationship rows for the table named by `mapping["table"]` (i.e. use `data["tables"][mapping["table"]]`); when it is already an array, use it directly. Each selected row has the columns named by the mapping (others are ignored), and the array may have any length. The mapping therefore also carries a `"table"` field naming the relation to read.

# B. Library (pinned — D3 v7)

Use D3 version 7 only, loaded from the official CDN inside the produced HTML:

```html
<script src="https://d3js.org/d3.v7.min.js"></script>
```

(plus any chart-specific official D3 plugin named in the chart section, also from an official CDN).

The API you write must match D3 v7. Do not use APIs removed in D3 v6+, in particular `d3.keys`, `d3.values`, `d3.entries`, `d3.map`, `d3.set`, `d3.nest`, or `d3.event`. Use plain JavaScript or current equivalents instead (`Object.keys`, `Map`, `Set`, `d3.group` / `d3.rollup`, and the event passed as the first argument to listeners). The file must run with no console errors against the loaded CDN version.

# C. Output requirements (shared by every chart)

1. One complete, standalone HTML file: `<!DOCTYPE html>` … `</html>`, never truncated. Because the program injects the data itself, completeness is structural.
2. Embed the data inline in the emitted HTML via `json.dumps`, so the file opens directly in a browser with no external data fetch.
3. Preserve the mapping exactly; read only the columns the mapping names; do not invent fields.
4. A short title (use `mapping["title"]` if present, otherwise a sensible default), readable labels, and explicit chart dimensions / margins so labels and marks are not clipped.
5. Escape any text taken from the data before placing it in HTML/SVG (e.g. via `html.escape`). This applies to **every data-derived string you inject via `json.dumps`** — node labels, link labels, category names, tooltip text — **not only the page title**. In particular, if a tooltip or any element is filled with `selection.html(...)` / `innerHTML`, every data value concatenated into it must **already be `html.escape`-d in Python**. Prefer `selection.text(...)` / `textContent` for raw data values, and reserve `.html()` for markup you control with only pre-escaped data interpolated in. Escaping the title while leaving `label` fields raw (because they "only go into the JS data array") is a defect — those labels still reach the DOM.
6. The emitted HTML/JavaScript must be self-contained: never reference a Python function, module, or variable inside the `<script>` (e.g. do not call `html.escape`/`html.unescape` in JS). Do all escaping and computation in Python, then embed the finished values via `json.dumps`; inside the browser use only JavaScript and D3.
7. Embed every data array the JavaScript needs (node names, matrices, link lists) into the page via `json.dumps`. The browser cannot see your Python locals — if the JS uses `names[i]` or a matrix, that array must have been injected into the script. Make each embedded JSON literal **script-safe**: the HTML parser ends the enclosing `<script>` at the first literal `</script>` (or `<!--`) *even inside a JS string*, and `json.dumps` does not escape `/`, so a data value containing `</script>` would break out of the page. After serialising, neutralise it — `json.dumps(x).replace("</", "<\\/")` — because JavaScript reads `<\/` as `/`, the runtime value is **unchanged** while the parser no longer sees a closing tag. Apply this to **every** `json.dumps` you inject into a `<script>` — ids, names, `source`/`target` keys and matrices alike, not only displayed labels — so an unescaped id/name string (e.g. a force-graph node id or a Sankey node name) cannot terminate the script.
8. The visualisation must be interactive. Hovering a primary mark (a node / arc / bar / slice that represents an entity instance, or a link / ribbon / flow that represents a relationship) must: (a) show a tooltip carrying the instance or relationship name(s) and the encoded value, and (b) visually emphasise the hovered mark and the marks connected to it while de-emphasising the rest, restoring on mouse-out. Implement this in plain D3 v7 (`selection.on('mouseover'|'mousemove'|'mouseout', (event, d) => …)`, with the event as the first argument); position a tooltip element from `event.pageX` / `event.pageY`.
9. Handle empty or degenerate data gracefully. If, after your aggregation, there is **nothing to draw** — zero nodes / rows / cells (e.g. no rows, or the mapped `source`/`target` columns are all null) — render a short **"No data to display"** message and return, instead of computing a layout. A layout built from zero elements divides by zero and yields `NaN` width/height, producing a blank or broken figure. Never emit a blank/`NaN` SVG for empty input; degrade to a readable message.
10. **Use a consistent light visual theme across the whole chart suite.** The page background must be **light** — near-white, e.g. `#ffffff` or a very light grey such as `#fafafa` / `#f7f8fa` — with **dark** text and muted-grey chrome. **Never use a dark or near-black background** (e.g. `#0f1117`) with light text: even if it looks striking for one chart, it makes that chart clash with every other renderer in the suite, which are all light. The data marks may use whatever colour encoding the chart-specific section defines, but the surrounding page, labels, axis lines and tooltips stay in this light palette so every chart looks consistent side by side.
11. Return the complete Python source for the module and nothing else — no prose, no commentary outside the code.

---

The chart-specific instructions below define the pattern, the mapping fields, the D3 construction, the required data transformation, and the chart's pitfalls. Implement exactly that chart on top of the shared contract above.

