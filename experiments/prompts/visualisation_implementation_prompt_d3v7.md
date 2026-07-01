# Mondial Visualisation Implementation Prompt (D3 v7, version-constrained)

You are generating a runnable web visualisation from an already classified Mondial schema-pattern task.

Your job is to implement the selected visualisation faithfully in the requested library.

Target library:

```text
{{TARGET_LIBRARY}}
```

Task and mapping:

```json
{{PATTERN_AND_MAPPING_RESULT}}
```

Data:

```json
{{DATA}}
```

Optional data filter:

```text
{{DATA_FILTER}}
```

Requirements:

1. Generate one complete runnable HTML file.
2. Use only the target library and its required official dependencies.
3. Keep all data inline in the HTML.
4. Preserve the selected mapping exactly. Do not invent fields.
5. If an optional data filter is provided, apply it before rendering and use only the filtered rows.
6. Use the selected chart type when the target library supports it.
7. If the target library cannot faithfully support the selected chart type, state that limitation in an HTML comment and implement the closest faithful alternative only if it preserves the same data mapping.
8. Include readable labels, dimensions, margins, and a short title.
9. Return code only.

D3-specific requirements (apply only when the target library is D3):

10. Target **D3 v7**. Load it from the official CDN: `https://d3js.org/d3.v7.min.js`. For a Sankey diagram also load `https://cdn.jsdelivr.net/npm/d3-sankey@0.12/dist/d3-sankey.min.js`.
11. The API you use MUST match the loaded version. Do **not** use APIs removed in D3 v6+, in particular `d3.keys`, `d3.values`, `d3.entries`, `d3.map`, `d3.set`, `d3.nest`, or `d3.event`. Use plain JavaScript or current equivalents instead (`Object.keys`, `Map`, `Set`, `d3.group`/`d3.rollup`, the event passed as the first argument to listeners).
12. For a Sankey diagram, build an explicit `nodes` array of objects and a `links` array whose `source`/`target` are either numeric node indices or set `sankey.nodeId(d => d.name)` so string ids resolve. Bind the flow value to the mapped weight attribute, and draw link paths with `d3.sankeyLinkHorizontal()`.
13. Ensure the file runs with no console errors against the loaded CDN versions.
