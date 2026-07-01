# Visualisation Implementation Rubric (Stage 3)

Score each generated standalone HTML against the fixed Stage 1+2 mapping it was given.
Stage 1+2 is held constant across models, so this rubric measures **implementation
ability only**. Score each criterion 0 / 1 / 2.

## Criteria

| Criterion | Score 0 | Score 1 | Score 2 |
| --- | --- | --- | --- |
| Runnability | Broken / truncated; will not render | Renders with console errors or missing pieces | Complete, self-contained, renders cleanly |
| Mapping fidelity | Wrong/invented fields | Uses the mapped fields but mis-encodes one (e.g. width not bound to `percentage`) | source=country, target=continent, width=percentage exactly as mapped |
| Data completeness | Drops most rows / hard-codes a sample | Inlines a partial subset | All applicable rows inlined and used |
| Chart-type faithfulness | Not the selected chart | Approximation with same mapping (limitation stated) | Faithful Sankey in the target library |
| Readability | Unlabelled / overlapping / unusable | Some labels, cluttered | Clear labels, title, margins; legible layout |
| Code quality | Extra/unofficial deps or hacks | Minor issues | Only official deps, data inline, no invented logic |

Maximum per generation: 12.

## Notes

- Truncation caused purely by the token cap (not a model error) should be re-run with a
  larger `--impl-max-tokens` before scoring; thinking traces compete with HTML for the budget.
- For `google_charts`, Sankey rows take the compact `['country','continent', percentage]`
  form, so the literal word "percentage" appears once (header) — count data rows, not the word.
