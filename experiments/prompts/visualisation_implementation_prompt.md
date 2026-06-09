# Mondial Visualisation Implementation Prompt

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

For many-many Sankey mappings, preserve this encoding:

- source node = the `k1` / source foreign-key field
- target node = the `k2` / target foreign-key field
- link width or weight = scalar relationship attribute `a1`
