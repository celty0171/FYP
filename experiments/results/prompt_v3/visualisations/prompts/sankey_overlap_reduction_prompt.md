# Sankey Overlap Reduction Prompt

You are generating a runnable web visualisation from an already classified schema-pattern task.

This prompt variant focuses on producing a readable Sankey diagram with minimal link overlap and visual clutter. It is general and should be applied to any Sankey-style many-many relationship, not only Mondial.

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
4. Preserve the selected Sankey mapping exactly:
   - source node = source/key field
   - target node = target/key field
   - link width or weight = scalar relationship attribute
5. If an optional data filter is provided, apply it before rendering and use only the filtered rows.
6. Do not invent fields or change the semantics of the weight.

Layout and readability requirements:

1. Minimise link overlap and crossings as far as the target library allows.
2. Sort source nodes deterministically by their main target group, then by total outgoing weight, then by label. This should cluster sources flowing to the same target.
3. For sources with multiple targets, place them near the boundary between their target groups so their secondary links travel shorter distances.
4. Sort target nodes by total incoming weight or a stable semantic order, and keep target labels readable.
5. Sort links within each source by target order, and within each target by source order, so links enter and leave nodes consistently.
6. Use sufficient vertical height and node padding. Avoid compressing many source nodes into a small canvas.
7. Use subtle link opacity and target-based link colours so overlapping links remain distinguishable without becoming visually heavy.
8. Use tooltips for exact values. Labels may be shortened only if the full label remains available in a tooltip.
9. If the target library does not expose enough control over node or link ordering, state this limitation in an HTML comment and still apply the best available controls.

Library-specific guidance:

- For D3 Sankey, explicitly set `nodeSort`, `linkSort`, `nodePadding`, `nodeWidth`, chart `extent`, and enough layout `iterations`. Use a custom ordering function rather than relying on default ordering.
- For Google Charts Sankey, sort the input rows before `data.addRows`; use a tall enough chart, clear node labels, and target-aware colours. Note in an HTML comment that Google Charts provides limited direct control over Sankey routing.
- For Vega or Vega-Lite, do not pretend that Vega-Lite has native Sankey support. If using Vega-Lite, state the limitation and implement a faithful alternative only if it preserves source, target, and weight semantics. If using Vega, implement ordering and link path control where possible.

Return code only.
