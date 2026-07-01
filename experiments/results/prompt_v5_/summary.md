# LLM Run Evaluation: prompt_v5_mcbrien

## Summary

- Pattern accuracy: 5/9 (55.6%)
- Schema evidence accuracy: 7/9 (77.8%)
- Visualisation overlap: 5/9 (55.6%)
- Exact visualisation set match: 1/9 (11.1%)

## Cases

| Case | Table | Expected | Actual | Pattern | Viz overlap | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | country | basic_entity | basic_entity | yes | bar_chart, choropleth_map, word_cloud | yes |
| 2 | economy | basic_entity_inherited_key | one_many_relationship | no | - | yes |
| 3 | lake | basic_entity | basic_entity | yes | bubble_chart, scatter_chart | yes |
| 4 | organization | basic_entity | basic_entity | yes | bar_chart, calendar_chart, word_cloud | no |
| 5 | country_population | weak_entity | one_many_relationship | no | - | yes |
| 6 | ethnic_group | weak_entity | weak_entity | yes | - | yes |
| 7 | airport | one_many_relationship | basic_entity | no | - | no |
| 8 | encompasses | many_many_relationship | many_many_relationship | yes | sankey_diagram | yes |
| 9 | borders | reflexive_many_many_relationship | many_many_relationship | no | chord_diagram | yes |
