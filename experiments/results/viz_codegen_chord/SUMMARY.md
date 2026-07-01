# viz_codegen_chord — Step 3 deterministic renderer (chord, D3 v7) — both relationship patterns

> **2026-06-30 — dual-pattern extension (supervisor request).** A chord now serves **both**
> `reflexive_many_many_relationship` *and* `many_many_relationship` (the Sankey cell does too; the two
> charts are interchangeable across the two patterns). `render_chord_reference.py` reads an optional
> `mapping["pattern"]`, else infers it from the data:
> - **reflexive** — sorted union node set, one rainbow colour per instance (unchanged behaviour).
> - **many_many** — **bipartite**: all `source` (`E1`) instances form one contiguous arc, all `target`
>   (`E2`) another; coloured by two distinct families (blues / oranges) with a legend. The symmetric
>   matrix only ever fills cross-group cells, so every ribbon runs between the two entity sets.
>
> Validated on Mondial: `encompasses` (`country` × `continent`, many_many) → 252×252 matrix, **0
> intra-group nonzero cells / 502 cross-group** (truly bipartite), legend `[country, continent]`;
> `borders` (reflexive) regression unchanged (`bipartite=false`, rainbow). Step-3 prompt
> `chart_chord.md` updated to cover both; Step-2 v3 prompt now recommends both charts for both
> patterns and adds `"pattern"` to the mapping. Cross mapping: `mapping_encompasses_chord.json`.
> See `encompasses_reference.html` (bipartite) and `borders_reference.html` (reflexive).

---

## (original) reflexive_many_many → chord, D3 v7

Second Step-3 cell after `viz_codegen_sankey`, and the first to use the **layered prompt** and a
real **D3 v7** target. Same paradigm: the model writes `render(mapping, rows) -> HTML` once; data is
read at run time and never enters the prompt.

## Layered prompt structure (`experiments/prompts/viz_codegen/`)

- `base_d3v7.md` — **shared base**, identical for every chart: the renderer contract
  (`render(mapping, rows)` + `--mapping/--data/--out`, std-lib only, data read at run time, column
  names from the mapping), the **D3 v7 version/API rules** (pin `d3.v7.min.js`; forbid `d3.keys`,
  `d3.nest`, `d3.event`, …), and the output rules (complete HTML, inline data via `json.dumps`,
  escape in Python, **no host-language functions in the emitted JS**, inject every array the JS
  needs).
- `chart_chord.md` — **chord-specific block**: reflexive semantics (one shared node set), mapping
  fields, the matrix transformation (union nodes → square symmetric N×N), the `d3.chord`/`arc`/
  `ribbon` recipe, label resolution via `names[d.index]`, pitfalls.
- `chart_sankey.md` — the Sankey cell re-expressed on the same base, migrated **Google Charts → D3
  v7 + d3-sankey@0.12** (node-id, namespaced source/target node sets — the contrast case to chord's
  shared set).

A full prompt = `base_d3v7.md` + one chart block, concatenated by the runner. The D3 version rules
live once and every chart inherits them.

## Data and mapping

- `mondial_borders_data.json` — 326 `borders` rows (`country1`, `country2`, `length`), generated via
  `convert_mondial_data_to_json.py --table borders`.
- `mapping_borders.json` — `{source: country1, target: country2, width: length}` from the validated
  Stage-1/2 case9 result (`prompt_v8_thinking/responses/case_9.json`, `reflexive_many_many` → chord).

## Reference renderer

`render_chord_reference.py` on `borders`: 169 union nodes, square **symmetric 169×169** matrix,
weight conserved (undirected double-count 522412.08), D3 v7 loaded, no forbidden APIs, complete HTML.
Confirms the contract is satisfiable in D3 v7. (169 nodes is dense but faithful; a readable chord
comes from passing a filtered regional data file, not from dropping data in the renderer.)

## Qwen3-14B provenance (port 8001, thinking off) — two operational findings + the hardening loop

**Attempt 1 — greedy repetition loop.** At `temperature=0` the model fell into a decoding loop,
emitting hundreds of `import importlib.util` / `import importlib.metadata` lines until it hit the
4096-token cap (`finish_reason=length`); no renderer was produced. Distinct from the thinking-mode
context overflow seen in Step 1. **Fix:** `repetition_penalty=1.1` (+ a base-prompt line "import only
what you use", + extraction that tolerates a truncated/unclosed code fence).

**Attempt 2 — runs as Python, broken in the browser.** With the loop fixed the renderer ran and
produced a complete 147 KB HTML that passed every *structural* check (complete, D3 v7, `d3.chord`/
`d3.ribbon`, no forbidden APIs, titled) — yet was browser-non-functional, with three bugs:
1. **2-D matrix flattened to 1-D** before injection (`matrix_flat`), then handed to `d3.chord()`,
   which indexes `matrix[i][j]` → NaN angles, nothing renders. (The Python had built the 2-D matrix
   correctly, then flattened it for no reason.)
2. **Python `html.unescape` called inside the JavaScript** → `ReferenceError` in the browser.
3. **The node-name array was never injected into the JS**, so labels could not resolve to names.

This is the documented *graph-construction / implementation-reasoning* axis, not a context problem
(the output fit comfortably). It also showed structural checks are **necessary but not sufficient**;
static JS-sanity checks were added (matrix is `[[...]]`, no Python funcs in `<script>`, names array
present).

**Attempt 3 — hardened prompt closes all three.** Three targeted guards were added: base now forbids
host-language functions in JS and requires every JS array to be injected; the chord block requires a
2-D `N×N` matrix (explicitly "do not flatten") and label resolution via `names[d.index]` (noting a
group's `.data` is the row sum, not the name). Re-running the *same* Qwen3-14B (thinking off,
`repetition_penalty=1.1`), no code edits:

| check | attempt 2 | attempt 3 (hardened) |
|-------|-----------|----------------------|
| Python funcs in JS | `html.unescape` ❌ | none ✓ |
| matrix injected | flat 1-D ❌ | **169×169 2-D, square** ✓ |
| names array in JS | absent ❌ | present, 169/169 ✓ |
| complete / D3 v7 / no forbidden APIs | ✓ | ✓ |

Code-level confirmation in `qwen_render_chord.py`: `json.dumps(nodes)` + `json.dumps(matrix)`
injected, `const matrix = [[…]]`, `chordLayout(matrix)` (2-D), `.text(d => names[d.index])`.

**Verdict (correctness phase):** as with Step 1 (8/9 → 9/9), the gap on the harder chord cell was
closed by **prompt hardening, not code edits** — but chord needed it, whereas Sankey worked first
try. The renderer quality scales with how explicitly the chart block pins the construction.
Operationally, the code-gen path needs `repetition_penalty` and thinking **off**.

## Interaction phase (added to the shared base, then re-tested)

The reference chord (and the prompt) originally had **no interactivity** — hovering a country did
nothing, because neither `base_d3v7.md` nor the rubric required it. A general interactivity clause
was added to the base output requirements (hover a mark → tooltip with name + value, emphasise the
hovered mark and connected marks, de-emphasise the rest, restore on mouse-out; plain D3 v7
`selection.on(...)`), so **every** chart cell inherits it. The reference renderer now implements it
(arc hover highlights a country's border ribbons + tooltip of total border length; ribbon hover
shows `A ↔ B (length)`).

Re-testing Qwen against the now-interactive base surfaced two **new** failure modes, both from the
larger embedded JS that interaction handlers add — and both fixed by base-level guards:

| re-run | failure | fix added to base |
|--------|---------|-------------------|
| 4 | renderer built HTML with a Python **f-string**; JS `{ }` / `${ }` → `SyntaxError` | forbid f-strings for the HTML |
| 5 | switched to `str.format()`; JS `{ }` → `KeyError` | forbid `.format()` too; allow **only** `+` concatenation or `str.replace` placeholders |
| 6 | — | **passes**: complete, D3 v7, 169×169 2-D matrix, names 169/169, no Python in JS, **and** interaction (2× mouseover/mouseout, tooltip at `event.pageX/Y`, raise+opacity highlight) |

Code-level confirmation (`qwen_render_chord.py`): HTML assembled by **line-by-line string
concatenation** (no f-string/`.format`); `mouseover` raises connected ribbons to opacity 1.0, dims
the rest to 0.2, positions the tooltip and shows the escaped country name.

**Lesson:** the renderer-authoring difficulty scales with **how much JavaScript the template
carries**. Interactivity roughly doubled the JS and pushed it past the brace-templating threshold,
exposing the f-string / `.format()` collisions the simpler renderers never hit. The shared base now
encodes the fix once for all cells: thinking off, `repetition_penalty=1.1`, no brace-based
templating, structural + static-JS validation, and the interactivity contract.

## Feasibility check — is the brace-templating guard load-bearing? (honest test)

To check whether the guard papers over a model limitation or fixes a real one, the base was reverted
to the version *without* the no-brace-templating bullet (interactivity still required) and the same
prompt was given to both a strong reference author and Qwen3-14B (temp 0, `repetition_penalty=1.1`).

| author | same un-guarded prompt | build method | result |
|--------|------------------------|--------------|--------|
| reference (careful author) | base(reverted) + chord | plain string concatenation (avoided the trap unprompted) | ✓ 169×169 symmetric matrix, complete, interactive, no regression |
| Qwen3-14B × 3 | same | **f-string all 3 times** | ✗ **0/3**, all `SyntaxError` |

**Conclusion: the gap is model capability, not prompt insufficiency.** The current prompt is already
enough for a careful author — the reference produced a correct, interactive chord with no brace guard,
spontaneously using concatenation. Qwen3-14B, by contrast, *deterministically* (3/3) reaches for an
f-string and breaks — not because it cannot write the chord logic (with the guard it reaches the
working result) but because it falls into the same Python string-assembly trap every time. So the
guard is **load-bearing for Qwen specifically**: it makes explicit an engineering habit a stronger
model carries implicitly. The guard was restored after this test
(`run_qwen_chord_unguarded.py`, `qwen_unguarded_{1,2,3}.py` keep the evidence).

## Reproduce

```bash
cd experiments
# reference
python3 results/viz_codegen_chord/render_chord_reference.py \
  --mapping results/viz_codegen_chord/mapping_borders.json \
  --data mondial_database/mondial_borders_data.json \
  --out results/viz_codegen_chord/borders_reference.html
# Qwen (needs SSH tunnel to 8001)
python3 results/viz_codegen_chord/run_qwen_chord.py
```

## Next

- Browser-render both chord HTMLs to confirm visual readability (checks here are structural + static
  JS, not pixels); try a regional subset data file for a legible chord.
- Re-validate the migrated `chart_sankey.md` (D3 v7) end-to-end like the chord cell.
- Continue the taxonomy: `one_many → treemap / circle packing`, `weak → line / stacked / spider`,
  `basic → bar / scatter / choropleth / word cloud`, one chart block each on the shared base.
- Carry forward the runner defaults proven here: thinking off, `repetition_penalty=1.1`,
  truncation-tolerant code extraction, structural **and** static-JS validation.
