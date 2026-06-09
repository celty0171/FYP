# LLM Run Evaluation: prompt_v2_clean_schema_2026_05_27

## Summary

- Pattern accuracy: 9/9 (100.0%)
- Schema evidence accuracy: 9/9 (100.0%)
- Visualisation overlap: 9/9 (100.0%)
- Exact visualisation set match: 1/9 (11.1%)

## Cases

| Case | Table | Expected | Actual | Pattern | Viz overlap | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | country | basic_entity | basic_entity | yes | bar_chart, choropleth_map, word_cloud | yes |
| 2 | economy | basic_entity_inherited_key | basic_entity_inherited_key | yes | scatter_chart | yes |
| 3 | lake | basic_entity | basic_entity | yes | bubble_chart, scatter_chart | yes |
| 4 | organization | basic_entity | basic_entity | yes | bar_chart, calendar_chart, word_cloud | yes |
| 5 | country_population | weak_entity | weak_entity | yes | line_chart | yes |
| 6 | ethnic_group | weak_entity | weak_entity | yes | grouped_bar_chart | yes |
| 7 | airport | one_many_relationship | one_many_relationship | yes | circle_packing, treemap | yes |
| 8 | encompasses | many_many_relationship | many_many_relationship | yes | sankey_diagram | yes |
| 9 | borders | reflexive_many_many_relationship | reflexive_many_many_relationship | yes | chord_diagram, network_chart | yes |
