# Stage 3 Visualisation Comparison — case8 (`encompasses`, many_many → Sankey)

Controlled comparison of **Qwen3-14B** vs **Qwen2.5-Coder-32B-Instruct** on the
visualisation-implementation step only. Stage 1+2 is held fixed: both models receive the
same validated mapping (`results/prompt_v8_thinking/responses/case_8.json` —
`source=country, target=continent, width=percentage`, Sankey). Same prompt
(`visualisation_implementation_prompt.md`), same 251-row data, temperature 0.

- Qwen3-14B: thinking **ON** (its best Stage 1+2 setting); Coder-32B: no thinking.
- Default servers: vLLM, **`max_model_len = 16384`** (this is the binding constraint). §7 adds a
  controlled 16k-vs-32k comparison using a second Qwen3-14B instance at `max_model_len = 32768`.

## Results

| Run | lib | thinking | sec | rows | complete | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3_14b_google_charts | google_charts | ON | 225 | 251 | ✅ | runs; missing `<title>` |
| coder_32b_google_charts | google_charts | – | 283 | 251 | ✅ | **best — complete, titled, robust** |
| coder_32b_d3 | d3 | – | 320 | 251 | ✅ | complete but **`d3.keys` removed in v7 → runtime error** |
| qwen3_14b_d3 | d3 | ON | 372 | 175 | ❌ | **truncated** — thinking + verbose data overran 16k |
| qwen3_14b_d3_compact | d3 | ON | 505 | 0 | ❌ | `<think>` never closed → reasoning leaked into the file |
| coder_32b_d3_v7 | d3 (version-constrained prompt) | – | 324 | 251 | ⚠️ | deprecated APIs gone, but **new graph-construction bug** (see §5) |
| qwen3_14b_d3_nothink_16k | d3 | – | 35 | 0 | ❌ | completes fast but **stubs the data** (`// ... data`) + old d3-sankey v1 API (see §6) |
| qwen3_14b_d3_32k | d3 | ON | 445 | 251 | ⚠️ | **32k fixes the truncation** — complete, all 251 rows, no leak — but still mixes `d3-sankey.v1` + `.layout()`/`.link()` (see §7) |
| qwen3_14b_google_charts_32k | google_charts | ON | 368 | 251 | ✅ | complete, all 251 rows; missing `<title>` (no change vs 16k — see §7) |

(Runnability is static analysis — not yet browser-verified.)

## Findings

1. **The 16k context window is the dominant factor for Stage 3, not raw model skill.**
   d3's verbose inline JSON + a long thinking trace do not co-fit in 16384 tokens. With full
   data Qwen3-14B's HTML is cut off mid-array; with compact data its `<think>` block never
   terminates and the reasoning leaks into the output.

2. **Thinking mode is a liability for Stage 3, the opposite of Stage 1+2.** Thinking won
   Stage 1+2 (short JSON, reasoning-bound). For Stage 3 the output is long HTML, so the
   thinking trace competes with the code for the token budget. Coder-32B with **no** thinking
   is the more reliable generator here.

3. **google_charts is more robust than d3 under a tight context.** Its Sankey rows use the
   compact `['country','continent', pct]` form, so all 251 rows fit comfortably and both
   models complete. Both google_charts outputs are the only cleanly-complete d3-or-google
   files; Coder-32B's is the best (complete + titled).

4. **Coder-32B's d3 has a real bug:** it uses `d3.keys()` (removed in d3 v6+) while loading
   d3 v7, and wires Sankey nodes by string name without `sankey.nodeId` — the classic d3 v4
   example that breaks on v7. Ironically Qwen3-14B's *intended* d3 code built nodes with a
   correct v7 `nodeMap` pattern, but it never emitted a clean file.

5. **Version-constrained follow-up (run `coder_32b_d3_v7`): the version error is
   prompt-steerable, but a separate graph-construction error is not.** To test whether the
   `d3.keys` failure in §4 is a *knowledge/version-alignment* problem rather than a coding-skill
   problem, a constrained d3 prompt
   (`prompts/visualisation_implementation_prompt_d3v7.md`) was added. It pins D3 to v7 and
   `d3-sankey@0.12`, and explicitly forbids the APIs removed in d3 v6+ (`d3.keys`, `d3.values`,
   `d3.entries`, `d3.map`, `d3.set`, `d3.nest`, `d3.event`), while requiring a proper node/link
   build with `sankey.nodeId` and `d3.sankeyLinkHorizontal()`. Coder-32B (no thinking) was re-run
   with this prompt only; everything else was held fixed.

   What improved (confirms the §4 diagnosis):
   - **Every named deprecated API disappeared** (`REMOVED-API used: NONE`). The model switched
     from `d3.keys()` to the v7-era `d3.group()`, and loaded matching CDN versions
     (`d3.v7.min.js` + `d3-sankey@0.12` from jsDelivr).
   - The file is complete (`</html>` present), inlines all 251 rows, has a `<title>`, and uses
     `d3.sankeyLinkHorizontal()`.
   - → The `d3.keys` runtime error is a **version/knowledge-alignment issue and is fully
     prompt-steerable.** Constraining the API surface eliminates it reliably.

   What still breaks (a different, deeper failure the constraint did not fix). The graph is built as:

   ```js
   const graph = {
       nodes: d3.group(data, d => d.country).map(([name]) => ({ name })),
       links: data.map(d => ({ source: d.country, target: d.continent, value: d.percentage }))
   };
   ```

   Three independent defects remain:
   1. **`d3.group(...)` returns a JS `Map`, which has no `.map()` method** → `TypeError:
      ...map is not a function` at runtime. The model adopted the correct *function* (`d3.group`)
      but treated its return value as an array.
   2. **Continent nodes are never created.** `nodes` is grouped by `d.country` only, so the
      `target: d.continent` references point at nodes that do not exist.
   3. **`source`/`target` are string names but `sankey.nodeId` is not set** (the prompt asked
      for it; the model omitted it), so d3-sankey — which defaults to numeric indices — cannot
      resolve the string ids even if the continent nodes existed.

   These are *graph-construction correctness* errors (building a correct bipartite node set and
   resolving link endpoints), not API-version errors. They survived the version constraint, so
   they reflect a genuine **implementation-reasoning gap** rather than stale knowledge.

   **Conclusion of the follow-up.** The single d3 failure from §4 actually decomposes into two
   distinct causes: (a) *deprecated-API / version drift* — caused by training data dominated by
   pre-v6 Sankey examples, and **fixable by prompt constraints** (verified here); and (b)
   *Sankey graph-construction logic* — the harder reasoning task, which the model still gets
   wrong even when the API surface is constrained. So "is Coder-32B's d3 bug a capability
   problem?" splits cleanly: the version part is **not** a capability gap (it is steerable);
   the graph-construction part **is**. A natural next step is to extend the constrained prompt
   with explicit node-set and `Array.from(d3.group(...))` guidance and re-test whether (b) is
   also steerable or is a true ceiling for this model.

6. **No-thinking control for Qwen3-14B d3 (run `qwen3_14b_d3_nothink_16k`): disabling thinking
   does NOT rescue Qwen3-14B's d3 — it just fails differently.** To separate the *context* effect
   from the *thinking* effect before testing a 32k server, Qwen3-14B was run on d3 at 16k with
   thinking **off** (everything else fixed). It finished in 35 s and produced a complete, titled
   file — but:
   - **It did not inline the data at all.** The data array is a placeholder comment:
     `const data = [ // ... (all data entries from the provided JSON) ];`. So 0 of 251 rows are
     present (violates the "keep all data inline" requirement). This is a *different* failure from
     the thinking runs (which at least tried to write every row before being truncated).
   - It also used d3-sankey v1/v4-era APIs removed in v6+ (`d3.map`, `sankey.link()`, `.layout()`).

   This sharpens the Qwen3-14B d3 picture at 16k: **every variant fails** — thinking-on truncates
   mid-data, thinking-on+compact never closes `<think>`, and thinking-off stubs the data. So "just
   turn thinking off" is not a fix for *this* model on d3 (unlike Coder-32B, whose no-thinking run
   did inline all 251 rows and only carried the `d3.keys` version bug). It also confirms Coder-32B
   is the stronger raw code generator here. The motivation for the 32k test therefore stands: it is
   specifically the *thinking-on* d3 path that a larger context could rescue.

7. **16k vs 32k context for Qwen3-14B (runs `qwen3_14b_d3_32k`, `qwen3_14b_google_charts_32k`):
   a larger context fixes the *completeness* failure but not the *version* failure — the two are
   orthogonal.** A second Qwen3-14B instance was deployed with `--max-model-len 32768` (a separate
   vLLM server on port 8011, single L40S; the 16k instance on 8001 was left untouched). Stage 3 was
   re-run with thinking **on**, everything else fixed, on both libraries.

   - **d3 + thinking is rescued on completeness.** At 16k this path *truncated* mid-array
     (175/251 rows, no `</html>` — §1) or, with compact data, *leaked* its `<think>` block into the
     file. At 32k it is **complete**: `</html>` present, **all 251 rows inlined**, **no thinking
     leak**, a `<title>`, 22.2 KB in 445 s. This directly confirms the §1 diagnosis that the binding
     failure at 16k was the *context window*, not model skill — give the thinking trace and the
     verbose inline JSON room to co-fit and the structural failure disappears.
   - **But the d3 version/API bug is unchanged by context.** The 32k d3 file still loads
     `d3-sankey.v1.min.js` against `d3.v7.min.js` and uses the v1-era `sankey.link()` / `.layout()`
     (no `sankey.nodeId`, no `d3.sankeyLinkHorizontal`). This is the **same class of
     knowledge/version-alignment error** seen in Coder-32B (§4–§5), and it is *orthogonal to context
     size*: a bigger window lets the model finish writing the wrong API, it does not correct it.
     Closing it needs the prompt constraints from §5, not more tokens.
   - **google_charts barely changes.** At 32k it is again complete with all 251 rows (21.7 KB,
     368 s) and again omits `<title>` — exactly as at 16k. Its compact Sankey rows already fit the
     16k budget (§3), so the extra context buys nothing here. This is the control that isolates the
     effect: 32k helps *only* the path that was context-bound (d3 + thinking), and does nothing for
     the path that already fit.

   **Conclusion of the 32k test.** Stage-3 failures decompose into two independent axes: (a) a
   *context-budget* axis — truncation / `<think>`-leak / data-stubbing — which **scales away with a
   larger window** (16k → 32k turns the truncated d3 run into a complete 251-row file); and (b) a
   *library-version/graph-construction* axis — deprecated APIs, wrong CDN pairing, malformed
   node/link building — which **does not respond to context at all** and remains prompt-work (§5).
   For these servers the practical takeaway is unchanged: prefer **Coder-32B + google_charts** for
   reliability; if d3 is required, 32k removes the completeness risk but the output still needs a
   version-constrained prompt to be runnable.

## Recommendation

For the visualisation-implementation step on these 16k servers:
- Prefer **Coder-32B, thinking off**.
- Prefer **google_charts** for many-row Sankey cases (or pass d3 data compactly / filtered).
- If d3 is required at full data, either raise the server `--max-model-len`, disable thinking,
  or apply a `--data-filter` to cut rows.
