# Area-Weighted Sankey Visualisation Prompt

You are generating a runnable web visualisation from an already classified schema-pattern task.

This prompt variant is for Sankey diagrams where the relationship table contains a percentage/share field and the source entity table contains a scalar size field such as area. The goal is to make link width and node size represent real source-size contribution rather than raw percentage alone.

The instructions are general. Mondial country-continent data is one example, but the same approach applies to any source-target relationship where:

- relationship rows contain `source`, `target`, and `percentage/share`
- source entity rows contain a source key and a scalar size attribute

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

Source entity data with size/area:

```json
{{SOURCE_ENTITY_DATA}}
```

Optional data filter:

```text
{{DATA_FILTER}}
```

## Core Requirements

1. Generate one complete runnable HTML file.
2. Use only the target library and its required official dependencies.
3. Keep all data inline in the HTML.
4. Use the selected source and target fields from the relationship mapping.
5. Join relationship rows to source entity rows using an explicit key match.
6. Compute a derived Sankey link weight:

```text
weighted_value = source_size * relationship_percentage / 100
```

7. Use `weighted_value`, not raw `relationship_percentage`, as the Sankey link width.
8. Preserve the original percentage/share in tooltips.
9. Preserve the source size/area in tooltips.
10. Show the computed weighted contribution in tooltips.
11. Do not invent missing source-size values. If a relationship row cannot be joined to a source entity row, omit that link and report the omitted rows in an HTML comment or visible note.
12. If an optional data filter is provided, apply it before rendering, then compute weighted values from the filtered relationship rows.
13. Return code only.

## Join-Key Requirements

Do not assume that the displayed source label is the correct join key.

Use the schema and data to identify the key shared by the relationship source field and the source entity table. For example, if relationship rows use a country code, join to `country.code`; if they use a country name, join to `country.name`.

The generated code must make the join key explicit, for example:

```text
relationship source field -> source entity key field
```

For Mondial `encompasses`, this commonly means:

```text
encompasses.country -> country.code
country.area -> source size
country.name -> optional readable display label
```

Use readable display labels when available, but never use a display label as the join key unless it is actually the matching key in the data.

## Sankey Mapping Requirements

Use this encoding:

- source node = relationship source field, optionally displayed with a joined readable label
- target node = relationship target field
- link width/weight = `weighted_value`
- tooltip = source label, target label, original percentage/share, source size/area, computed weighted contribution

The original relationship percentage is no longer the visual weight. It is supporting information used to calculate the area/size contribution.

## Interpretation Requirements

1. A source node's height should be proportional to the sum of its outgoing `weighted_value` links.
2. If all relationship rows for a source are included and the percentages sum to 100, the source node height is proportional to the source's full size/area.
3. If the data is filtered to only some targets, the source node height represents only the filtered contribution, not the full source size/area. State this clearly in the title, subtitle, or note.
4. A target node's height should be proportional to the sum of incoming `weighted_value` links.
5. For area data, target node height represents total area assigned to that target.
6. If percentages for a source do not sum to approximately 100 in the displayed data, do not silently normalise them. Use the given percentage values and mention the partial/overcomplete total in a note or tooltip.

## Layout and Readability Requirements

Use the same readability standards expected of a polished Sankey diagram:

1. Sort target nodes by total incoming `weighted_value`, or by a clear semantic order if one is provided.
2. Compute a weighted target barycentre for each source and sort sources by that barycentre to reduce crossings:

```text
source_barycentre = sum(weighted_value * target_rank) / sum(weighted_value)
```

3. Place multi-target sources near the boundary between their target groups.
4. Sort links within each source by target order and within each target by source order.
5. Use sufficient vertical height, generous node padding, and moderate link opacity.
6. Use target-based colours or another consistent group-based colour strategy.
7. Use labels that remain readable when source size varies greatly.
8. Add hover tooltips and highlighting where practical.

## Library-Specific Guidance

### D3 Sankey

If the target library is D3:

1. Use `d3-sankey`.
2. Build links with `value: weighted_value`.
3. Use `nodeId`, `nodeAlign(d3.sankeyLeft)`, `nodeWidth`, `nodePadding`, `extent`, `iterations`, `nodeSort`, and `linkSort`.
4. Precompute node ordering from weighted values, not raw percentages.
5. Use `d3.sankeyLinkHorizontal()` for paths.

### Google Charts Sankey

If the target library is Google Charts:

1. Pass `weighted_value` as the third column in `data.addRows`.
2. Sort input rows using the weighted ordering strategy before adding rows.
3. Configure node padding, node width, colours, labels, and chart height.
4. Add an HTML comment noting that Google Charts provides limited direct control over exact routing and node ordering.

### Vega / Vega-Lite

If the target library is Vega:

1. Compute `weighted_value` before layout.
2. Use explicit node/link positioning where possible.

If the target library is Vega-Lite:

1. Do not claim native Sankey support.
2. State the limitation in an HTML comment.
3. Implement a faithful alternative only if it preserves source, target, and `weighted_value` semantics.

## Output

Return the complete runnable HTML code only.
