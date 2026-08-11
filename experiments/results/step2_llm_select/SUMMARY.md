# Step 2 — LLM chart selection vs deterministic rule pick

Offline comparison over the 9 blind cases. Both picks are scored against the gold 
`expected_visualisations` (a hit = the picked chart is in the gold set, after alias 
normalisation). Gold is read only during scoring, after predictions are written, so the 
selector never sees it.

| metric | value |
|---|---|
| cases | 9 |
| deterministic (rule) hits | 7/9 |
| LLM hits | 9/9 |
| rule/LLM agreement | 7/9 |
| LLM answered by model | 9/9 |

| case | pattern | gold | rule pick | ✓ | LLM pick | ✓ | src | reason |
|---|---|---|---|:-:|---|:-:|---|---|
| 1 | basic_entity | bar_chart, choropleth_map, word_cloud | bar chart | ✓ | bar chart | ✓ | llm | A bar chart effectively compares the scalar population values across the 246 distinct country codes. |
| 2 | basic_entity_inherited_key | scatter_chart | bar chart | · | scatter diagram | ✓ | llm | A scatter plot effectively reveals the relationship between two continuous variables across 246 countries without the clutter of a 246-bar chart. |
| 3 | basic_entity | bubble_chart, scatter_chart | bar chart | · | scatter diagram | ✓ | llm | A scatter plot effectively shows the relationship between elevation and depth for 223 lakes, avoiding bar chart overcrowding and the high null rate in dam_height. |
| 4 | basic_entity | bar_chart, calendar_chart, word_cloud | calendar chart | ✓ | calendar chart | ✓ | llm | The calendar chart is the only candidate and effectively maps the primary key and temporal columns to visualize establishment dates. |
| 5 | weak_entity | line_chart | line chart | ✓ | line chart | ✓ | llm | A line chart best captures temporal trends over years, while a grouped bar chart would be entirely unreadable with 246 countries and 161 years. |
| 6 | weak_entity | grouped_bar_chart | grouped bar chart | ✓ | grouped bar chart | ✓ | llm | A grouped bar chart compares the percentage distribution of ethnic group names across countries, matching the weak entity relationship. |
| 7 | one_many_relationship | circle_packing, treemap | tree map | ✓ | tree map | ✓ | llm | A tree map best displays the hierarchical relationship and scalar measure via space-efficient rectangles, outperforming circle packing and hierarchy tree. |
| 8 | many_many_relationship | sankey_diagram | Sankey diagram | ✓ | Sankey diagram | ✓ | llm | Sankey diagram effectively visualizes the distribution of countries across 6 continents with proportional flows, avoiding the clutter of a 250-node force graph or a sparse matrix. |
| 9 | reflexive_many_many_relationship | chord_diagram, network_chart | chord diagram | ✓ | chord diagram | ✓ | llm | Chord diagrams effectively display weighted many-to-many relationships like border lengths between countries in a compact, readable circular layout. |
