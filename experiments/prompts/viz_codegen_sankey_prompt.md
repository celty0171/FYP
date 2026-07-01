You are an expert in schema-driven data visualisation and front-end code generation, working on the Mondial visualisation project.

Your task is **not** to draw one chart for one dataset. Your task is to **write a deterministic Python program** that renders a Sankey diagram for **any** many-many relationship selection, given a chart mapping and the relationship rows at run time. The model is used once to author the renderer; thereafter rendering is reproducible code. Crucially, the data is supplied to the program as a file at run time — it is **not** embedded in this prompt, and your program must not assume any particular dataset, country set, or row count.

# 1. Pattern and chart context

This renderer serves the `many_many_relationship` schema pattern, whose visualisation is a **Sankey diagram**. The relationship connects instances of two entities `E1` (source) and `E2` (target); a scalar relationship attribute sets the width of the flow between them. Left-hand nodes are instances of `E1`, right-hand nodes are instances of `E2`, and the flow width encodes the scalar attribute.

# 2. Library (pinned)

Use **Google Charts** with the `sankey` package, loaded from the official Google loader:

```html
<script type="text/javascript" src="https://www.gstatic.com/charts/loader.js"></script>
```

and `google.charts.load('current', {'packages':['sankey']});`. Do not use D3 or any other charting library. Pinning the library here means every rendered file is consistent and runnable; do not introduce version-sensitive or deprecated APIs.

# 3. Inputs the program reads at run time

**Mapping** (the `--mapping` file): a JSON object describing the schema-to-chart encoding. It contains at least:

```json
{ "source": "country", "target": "continent", "width": "percentage" }
```

`source`, `target`, and `width` are the **names of the columns** in the data rows that carry, respectively, the `E1` key, the `E2` key, and the scalar flow attribute. An optional `"title"` string may also be present. The program may also accept the full Stage-1/2 result object and read the encoding from its `chart_mapping` (or `selected_visualisation.encoding`) field if a bare mapping is not given — but reading `{source, target, width}` is sufficient. Never hard-code the column names `country`/`continent`/`percentage`; always take them from the mapping.

**Data** (the `--data` file): a JSON array of row objects, e.g. `[{"country": "AL", "continent": "Europe", "percentage": 100}, ...]`. Each row has the three columns named by the mapping (plus possibly others, which are ignored). The array may have any length.

# 4. What the program must produce

A single, complete, standalone HTML file that draws the Sankey diagram, with:

- All rows rendered — because the program injects the data itself, completeness must be structural, never truncated.
- Source nodes = distinct `mapping["source"]` values, target nodes = distinct `mapping["target"]` values, flow width = the `mapping["width"]` value. Read only those three columns from each row; do not invent fields.
- Rows that share the same (source, target) pair summed into a single flow (Sankey links must be unique per source-target pair).
- A short title (use `mapping["title"]` if present, otherwise a sensible default such as "<source> → <target> Sankey diagram"), readable node labels, and explicit chart dimensions / margins so labels are not clipped.
- Data embedded inline in the emitted HTML via `json.dumps`, so the file is self-contained and opens directly in a browser.

# 5. Program interface (contract)

Write a single self-contained Python module, **standard library only**, deterministic (no randomness, no network calls at generation or render time beyond the pinned Google loader inside the produced HTML). It must:

- Expose a function `render(mapping: dict, rows: list[dict]) -> str` that returns the complete HTML document as a string.
- Provide a CLI `--mapping <file> --data <file> --out <file>` that loads the mapping and data JSON, calls `render`, and writes the HTML to `--out`.
- Run as-is under `python3 <module>.py --mapping ... --data ... --out ...` and produce a browser-openable file regardless of how many rows the data has.

# 6. Output

Return the complete Python source for the module and nothing else — no prose, no explanation, no commentary outside the code.
