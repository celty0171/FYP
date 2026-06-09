You are implementing a visualisation from an already selected schema-pattern mapping.
Target library: D3.js
Task: The selected visualisation is a chord diagram.

Mapping:

* source = <SOURCE_FIELD>
* target = <TARGET_FIELD>
* weight = <WEIGHT_FIELD>

Data: <DATA_FILE>

Additional instruction: <INSTRUCTION>

Requirements:

Generate one complete runnable HTML file.
Use only D3.js and its official dependencies.
Keep all data inline in the HTML.
Preserve the mapping exactly (source = country1, target = country2, weight = length). Do not remap to unrelated columns.
Do not invent fields or aggregate incorrectly. Build a symmetric matrix from the raw weights.
Include readable labels and a title.
Sizing & responsiveness. The chord ring must fill the available width. Compute the SVG side from the container width (e.g. clientWidth), not a hard-coded cap; if a max is needed, make it large (≥ 900 px). Set the SVG to width:100%, height:auto, and drive all geometry through the viewBox so it scales with the container.
Radius budget as a ratio, not fixed pixels. Derive outerRadius as a fraction of the half-size (e.g. outerR = size/2 * 0.78) and reserve label space proportionally, so the ring stays large at any canvas size instead of shrinking when padding is constant.
Tight viewBox / minimal margins. Centre the diagram and trim the viewBox to the actual content bounding box (ring + outermost labels). No large empty border around a small ring; leave no more than ~one ring-radius of empty margin on any side.
Label legibility & density. Place labels just outside the ring with consistent radial offset and rotation. If labels would overlap or collide with tick text, increase the ring radius or thin the tick density rather than shrinking the ring. Tick-scale text must not visually compete with the category labels.
Layout balance. The ring is the dominant element on the page; title and caption support it, not crowd it.
Size floor (verifiable). The rendered ring diameter should occupy at least ~70 % of the smaller dimension of its container.
Return code only.