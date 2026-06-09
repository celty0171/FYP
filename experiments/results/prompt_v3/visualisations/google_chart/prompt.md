You are implementing a visualisation from an already selected schema-pattern mapping.
Target library: Google Charts
Task:
The selected visualisation is a sankey diagram.
Mapping:
- source = country
- target = continent
- weight = percentage
Data:
mondial_data.json
Requirements:
1. Generate one complete runnable HTML file.
2. Use only Google Charts and its official dependencies.
3. Keep all data inline in the HTML.
4. Preserve the mapping exactly:
   - source column: country
   - target column: continent
   - weight column: percentage
5. Do not invent fields or aggregate incorrectly.
6. Include readable labels and a title.
7. Return code only.