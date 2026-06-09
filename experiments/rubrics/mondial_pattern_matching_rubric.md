# Mondial Pattern Matching Rubric

Score each LLM response against the expected Hannan/VizER-style DATA-FIRST case in `inputs/mondial_gold_patterns.json`.

## Criteria

| Criterion | Score 0 | Score 1 | Score 2 |
| --- | --- | --- | --- |
| Schema elements | Misses selected table/columns | Identifies some required elements | Identifies selected columns, PK columns, FK columns, and scalar attributes |
| Cardinality reasoning | Incorrect or absent | Partially infers one-many/many-many/weak entity | Correctly explains pattern from Hannan's PK/FK rules |
| Pattern classification | Wrong pattern | Plausible but underspecified | Correct visualisation schema pattern |
| Inherited-key reasoning | Misclassifies inherited-key cases | Mentions inherited key vaguely | Correctly distinguishes inherited-key basic entity from weak entity |
| Visualisation choice | Unsuitable chart | Suitable chart but weak justification | Suitable chart tied to schema pattern |
| Chart mapping | Missing/invalid mapping | Partial mapping | Complete chart-ready mapping |

Maximum score per case: 12.

## Notes

Prefer explanations that ground claims in schema evidence, not only chart intuition.
