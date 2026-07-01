# viz_codegen_sankey_d3 — Step 3 deterministic renderer (Sankey, D3 v7) — both relationship patterns

> **2026-06-30 — dual-pattern extension (supervisor request).** A Sankey now serves **both**
> `many_many_relationship` *and* `reflexive_many_many_relationship`. The namespaced `src:` / `tgt:`
> node identities already make this correct with **no structural change**: for `many_many` the two
> columns are different entity sets; for `reflexive` they are the same set drawn as a **directed flow**,
> so an instance legitimately appears on both sides (its "as source" and "as target" roles) as two
> namespaced nodes. `render_sankey_reference.py` reads an optional `mapping["pattern"]`, else infers
> reflexive when the source/target value sets overlap, and uses it only to phrase the subtitle.
> Validated on `borders` (reflexive) → 119 source / 130 target nodes, 80 labels appearing on both
> sides (correct directed flow); `encompasses` (many_many) regression unchanged. Step-3 prompt
> `chart_sankey.md` updated to cover both; cross mapping `mapping_borders_sankey.json`; see
> `borders_reference.html`.

---

## (original) many_many → Sankey, D3 v7

The Sankey cell re-authored on the **layered prompt** (`prompts/viz_codegen/base_d3v7.md` +
`chart_sankey.md`) and **D3 v7** (the original `viz_codegen_sankey/` pilot was Google Charts; that
dir is kept intact). Same paradigm as the other cells: the model writes `render(mapping, rows) ->
HTML` once; data is read at run time and never enters the prompt.

## Inputs

- `mapping_encompasses.json` — `{table: encompasses, source: country, target: continent, width:
  percentage, title: …}`. The `table` field selects the relation from the grouped database.
- Data: the full **`mondial_database/mondial_data.json`** (grouped `{"tables": {...}}`); the renderer
  selects `data["tables"]["encompasses"]` (251 rows).

## Renderer

`render_sankey_reference.py` — D3 v7 + `d3-sankey@0.12`, std-lib only, HTML assembled by plain
string concatenation (no f-string / `str.format`, per the base contract). Key construction:

- **Namespaced node ids** (`src:` / `tgt:`) so a country and a continent that share a string are not
  merged — `source` and `target` are two different entity sets.
- Links aggregated per `(source, target)` pair (width summed); `d3.sankeyLinkHorizontal()` paths.
- `_rows_for()` accepts a flat array or the grouped DB selected by `mapping["table"]`.
- Hover interaction (base contract): hover a node → highlight the flows touching it + tooltip of its
  total; hover a link → `source → target (value)`.

## Overlap-reduction layout (from `prompt_v4/.../sankey_overlap_reduction_prompt.md`)

A deterministic Step A–C ordering, attached to nodes as an integer `order` and driven through
d3-sankey (`nodeSort` / `linkSort` / `nodeAlign(d3.sankeyLeft)` / `iterations(32)`):

- **Step A — target affinity seriation.** Affinity of two targets = `Σ_sources min(w_to_Ti, w_to_Tj)`;
  greedy nearest-neighbour chaining places high-affinity targets adjacent. On encompasses this puts
  **Asia and Europe adjacent** (ranks 1, 2), so Russia's two links become a short hop, not a long
  crossing.
- **Step B — source weighted barycentre.** `barycentre = Σ(w·target_rank)/Σ(w)`, sorted by barycentre
  → outgoing weight → label. This clustered each continent's countries into a **perfectly contiguous
  block** (rank span == country count, density **1.00** for all six continents).
- **Step C — link order** via `linkSort` using node `order`.
- Visual: tall canvas (`max(sources, targets)·14`), generous `nodePadding`, links coloured by target
  group, partial opacity, **thin minor links drawn on top**, subtitle stating what width represents.

**Result:** the avoidable crossings are reduced to **zero** — single-continent countries flow straight
across in continent blocks; only Russia's secondary Europe link is a residual crossing, which is
topologically unavoidable in a 1-D Sankey and is minimised (adjacent groups) and hover-traceable.

Correctness is preserved throughout: 251 links == 251 unique pairs, width sum 24600.0, Russia split
(Asia 76.85 / Europe 23.15).

## Reproduce

```bash
cd experiments
python3 results/viz_codegen_sankey_d3/render_sankey_reference.py \
  --mapping results/viz_codegen_sankey_d3/mapping_encompasses.json \
  --data mondial_database/mondial_data.json \
  --out results/viz_codegen_sankey_d3/encompasses_reference.html
```

## Status / next

- Reference done and validated (structural + ordering metrics). Qwen run deferred until the
  code-specialised Coder-32B (port 8004) is available; the runner/prompt are ready.
- Carries the shared-base defaults: D3 v7, data from the grouped DB via `mapping["table"]`, no
  brace templating, interactivity, structural + static-JS validation.
