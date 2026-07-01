# viz_codegen_sankey — Step 3 as deterministic programming (many_many → Sankey pilot)

## Hypothesis

Step 3 (visualisation implementation) can be turned from a per-case LLM generation into a
**deterministic program**, the same move proven for Step 1 in `prompt_v9_codegen`. Instead of
asking the model to draw one chart for one dataset (data inlined in the prompt → context-window
bound, non-reproducible), ask it once to **write a renderer** `render(mapping, rows) -> HTML`. The
data is supplied to the program at run time and **never enters the prompt**, so completeness is
structural and the chart library is pinned once.

This directly attacks both Stage-3 failure axes documented in `PROJECT_STATUS.md`:
- **context-budget axis** (truncation / `<think>`-leak / data-stubbing) — *dissolved*: data is not
  in the prompt, so output size is independent of row count.
- **library-version axis** (deprecated APIs, wrong CDN pairing) — *pinned once* in the template.

## Method

- `experiments/prompts/viz_codegen_sankey_prompt.md` — Step-3 analogue of prompt_v9: pins Google
  Charts Sankey, defines the `render(mapping, rows) -> str` + `--mapping/--data/--out` contract,
  states that column names come from the mapping (not hard-coded) and data is read at run time.
- `mapping_encompasses.json` — the chart mapping `{source: country, target: continent, width:
  percentage}` taken from the validated Stage-1/2 case8 result (`prompt_v8_thinking/responses/case_8.json`).
- `render_sankey_reference.py` — reference renderer (this run; strong reference model).
- `run_qwen_sankey.py` — sends the prompt to self-hosted `Qwen3-14B` @ 8001 (thinking off,
  temperature 0), extracts the returned module, runs it on the 251-row `encompasses` data.

Data: `mondial_database/mondial_encompasses_data.json` (251 rows, the dataset that **truncated**
under the per-case paradigm at 16k — see `viz_case8/COMPARISON.md`).

## Result

| renderer | time | runs? | HTML complete | title | loader pinned | links | width sum |
|----------|------|-------|---------------|-------|---------------|-------|-----------|
| reference | — | yes | yes | yes | yes | 251/251 | 24600.0 ✓ |
| **Qwen3-14B (thinking off)** | **42 s** | **yes** | **yes** | **yes** | **yes** | **251/251** | **24600.0 ✓** |

Both renderers emit all 251 links with the width sum preserved, and both correctly handle the only
multi-continent country (Russia → Europe 23.15, Asia 76.85). Qwen's file is complete
(`<!DOCTYPE>`…`</html>`), titled, uses the pinned `gstatic` loader and the `sankey` package, and
escapes labels with `html.escape`.

**Headline:** on the exact dataset that previously truncated under per-case generation, Qwen3-14B
(thinking off) now produces a complete, runnable, data-complete 251-link Sankey — because the data
never entered the prompt. The renderer-generation paradigm removes the context-budget axis by
construction.

### Code-quality note (not a correctness issue)

Qwen emits 251 separate `data.addRows([[...]])` statements instead of one batched `addRows([...])`,
and builds an unused `node_to_index` map (dead code). Functionally correct and complete; only a
style/efficiency observation. The reference renderer injects the link array once via `json.dumps`.

## Reproduce

```bash
cd experiments
# reference
python3 results/viz_codegen_sankey/render_sankey_reference.py \
  --mapping results/viz_codegen_sankey/mapping_encompasses.json \
  --data mondial_database/mondial_encompasses_data.json \
  --out results/viz_codegen_sankey/encompasses_reference.html
# Qwen (needs SSH tunnel to 8001)
python3 results/viz_codegen_sankey/run_qwen_sankey.py
```

## Next

- Render in a real browser to confirm visual readability (the checks above are structural, not
  visual); the per-case `viz_case8` Sankeys are the aesthetic baseline to match or beat.
- Extend the renderer-generation prompt to the other taxonomy cells: `reflexive_many_many → chord`,
  `one_many → treemap / circle packing`, `weak_entity → line / stacked bar / spider`,
  `basic_entity → bar / scatter / choropleth / word cloud`. One renderer per (pattern × chart type).
- Optionally re-test on Coder-32B @ 8004 (code-specialised) when that tunnel is available.
- Thinking stays **off** for the code-gen path (per `prompt_v9_codegen` and the 16k overflow).
