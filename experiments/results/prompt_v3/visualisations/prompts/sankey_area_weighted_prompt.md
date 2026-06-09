# Area-Weighted Sankey Prompt

You are generating a runnable web visualisation from an already classified schema-pattern task.

This prompt variant changes the Sankey weight semantics from raw percentage to real area contribution. It is intended for cases where a relationship attribute gives a percentage share and the source entity has a scalar size attribute such as area.

Target library:

```text
{{TARGET_LIBRARY}}
```

Task and mapping:

```json
{{PATTERN_AND_MAPPING_RESULT}}
```

Relationship data:

```json
{{RELATIONSHIP_DATA}}
```

Source entity data with area:

```json
{{SOURCE_ENTITY_DATA}}
```

Optional data filter:

```text
{{DATA_FILTER}}
```

Requirements:

1. Generate one complete runnable HTML file.
2. Use only the target library and its required official dependencies.
3. Keep all data inline in the HTML.
4. Join relationship rows to source entity rows using the relationship source key and the source entity key.
5. Compute a derived link weight:

```text
area_weight = source.area * percentage / 100
```

6. Use `area_weight`, not raw `percentage`, as the Sankey link width.
7. Preserve the original percentage in tooltips, along with source area and computed area contribution.
8. Do not invent missing area values. If a source row has no matching area, omit that link and report the omission in an HTML comment or visible note.
9. If an optional data filter is provided, apply it before rendering, but compute area weights only from rows that remain after filtering.

Mapping requirements:

- source node = source/key field from the relationship table
- target node = target/key field from the relationship table
- link width or weight = `area_weight`
- tooltip fields should include source label, target label, original percentage, source area, and computed area contribution

Interpretation requirements:

1. The left-side source node size should be proportional to the sum of its outgoing `area_weight` values.
2. If all relationship rows for a source are included and the percentages sum to 100, the source node size will be proportional to actual source area.
3. The right-side target node size should be proportional to the sum of incoming `area_weight` values, representing total area assigned to that target.
4. If the data is filtered to only one target, source node sizes represent the area contribution to that filtered target, not full source area. State this in the title or subtitle.

Layout and readability requirements:

1. Sort source nodes by target group and descending `area_weight` to reduce crossings.
2. Use target-based colours and moderate link opacity.
3. Use sufficient vertical height and node padding.
4. Use readable labels and a title that explicitly says the diagram is area-weighted.
5. If the target library has limited Sankey ordering control, state this limitation in an HTML comment.

Example for Mondial `encompasses`:

- relationship source key = `country`
- relationship target key = `continent`
- relationship percentage = `percentage`
- source entity table = `country`
- source entity key = `code`
- source area = `area`
- computed link weight = `country.area * encompasses.percentage / 100`

Return code only.
