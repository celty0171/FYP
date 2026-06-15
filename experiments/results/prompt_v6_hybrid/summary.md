# LLM Run Evaluation: prompt_v6_hybrid

## Summary

- Pattern accuracy: 9/9 (100.0%)
- Schema evidence accuracy: 3/9 (33.3%)
- Visualisation overlap: 9/9 (100.0%)
- Exact visualisation set match: 2/9 (22.2%)

## Cases

| Case | Table | Expected | Actual | Pattern | Viz overlap | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | country | basic_entity | basic_entity | yes | bar_chart, choropleth_map | yes |
| 2 | economy | basic_entity_inherited_key | basic_entity_inherited_key | yes | scatter_chart | no |
| 3 | lake | basic_entity | basic_entity | yes | bubble_chart, scatter_chart | yes |
| 4 | organization | basic_entity | basic_entity | yes | bar_chart, calendar_chart, word_cloud | no |
| 5 | country_population | weak_entity | weak_entity | yes | line_chart | no |
| 6 | ethnic_group | weak_entity | weak_entity | yes | grouped_bar_chart | yes |
| 7 | airport | one_many_relationship | one_many_relationship | yes | circle_packing, treemap | no |
| 8 | encompasses | many_many_relationship | many_many_relationship | yes | sankey_diagram | no |
| 9 | borders | reflexive_many_many_relationship | reflexive_many_many_relationship | yes | chord_diagram | no |
