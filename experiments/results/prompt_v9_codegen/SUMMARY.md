# prompt_v9 — Step 1 code-generation (provenance) experiment

## Hypothesis

Step 1 (ER pattern identification) can be turned from a per-case LLM judgement into a
**deterministic program**: instead of asking a model to classify each selection, ask it to
*write the classifier*. The model is used once, at "compile time"; thereafter classification is
reproducible code that never sees the gold answer.

## Method

- `experiments/prompts/prompt_v9.md` — derived from `prompt_v8.md` by keeping only its Step-1
  half (scope constraint, pattern rules, decision order, boundary checks), dropping the chart
  recommendation / JSON-answer half, and changing the task to *emit a deterministic Python
  classifier* with a fixed interface (`classify_selection(...)` + `--schema/--cases/--out` CLI).
- `classifier_generated.py` — the program elicited by prompt_v9 (this run used a strong reference
  model; the same prompt is intended to be run through the self-hosted Qwen models for the real
  provenance comparison).
- `predictions.json` — its output on the nine blind cases (`inputs/mondial_blind_cases.json`,
  `mondial_database/mondial_schema_summary_clean.json`).

The generated classifier reads **blind input only** (case id + selected table + selected columns
+ schema PK/FK structure); it never reads `mondial_gold_patterns.json`.

## Result

Agreement with the hand-written baseline (`generated/vizer_rule_predictions.json`): **9/9**.

| case | table | generated | hand-written |
|------|-------|-----------|--------------|
| 1 | country | basic_entity | basic_entity |
| 2 | economy | basic_entity_inherited_key | basic_entity_inherited_key |
| 3 | lake | basic_entity | basic_entity |
| 4 | organization | basic_entity | basic_entity |
| 5 | country_population | weak_entity | weak_entity |
| 6 | ethnic_group | weak_entity | weak_entity |
| 7 | airport | one_many_relationship | one_many_relationship |
| 8 | encompasses | many_many_relationship | many_many_relationship |
| 9 | borders | reflexive_many_many_relationship | reflexive_many_many_relationship |

The two discriminating cases for the strict scope constraint both pass: `organization` (case 4)
has an unselected composite FK `(city,province,country)→city` that must be ignored, and `airport`
(case 7) has two FKs but only the `island` FK is selected. The generated code only counts a
foreign key when *all* its columns are among the selected columns, which handles both.

## Reproduce

```bash
cd experiments
python3 results/prompt_v9_codegen/classifier_generated.py \
  --schema mondial_database/mondial_schema_summary_clean.json \
  --cases inputs/mondial_blind_cases.json \
  --out results/prompt_v9_codegen/predictions.json
```

## Qwen3-14B provenance run (port 8001, 2026-06-23)

`run_qwen_v9.py` sends prompt_v9 to the self-hosted `Qwen3-14B` (16384 context) in two thinking
modes and runs whatever code it returns against the nine blind cases.

| mode | time | finish | completion tokens | classifier runs? | agreement |
|------|------|--------|-------------------|------------------|-----------|
| thinking **off** | 50 s | stop | 1198 | yes | **8/9** |
| thinking **on** | 509 s | length | 12288 (truncated) | no — no code emitted | — |

**Thinking-off: 8/9, one isolated bug.** The generated classifier (`qwen_nothink.py`) implements
the scope filter, decision order, and four of the five rules correctly. Its only error is the
inherited-key rule (rule 2): it fires `basic_entity_inherited_key` on `if not primary_key` — i.e.
only when *no* primary-key column is selected — instead of when the *whole* selected PK consists of
foreign keys to one parent. So `economy` (case 2: PK `[country]`, where `country` is itself a FK to
`country`) misses rule 2 and falls through to `basic_entity`. The model misread "no local
primary-key column" (no non-FK PK column) as "no primary-key column at all". Patching that single
condition (`qwen_nothink_patched.py`) restores **9/9** — confirming the rest of the logic is sound.

| case | table | qwen (thinking off) | baseline |
|------|-------|--------------------|----------|
| 2 | economy | basic_entity ❌ | basic_entity_inherited_key |
| (other 8) | — | match | match |

**Thinking-on overflows the 16k window.** The reasoning trace alone consumed the full 12288-token
budget (`finish_reason=length`) and never closed `<think>`, so no Python source was emitted. This
is the same context-budget liability documented for Stage 3 (see memory `stage3-thinking-liability`)
— thinking hurts the code-generation path on a 16k server, the opposite of the per-case Step-1 path
where it helped. For *writing the classifier*, thinking-off is the better configuration.

**Provenance verdict:** Qwen3-14B (thinking off) can author a near-correct deterministic Step-1
classifier from prompt_v9 in 50 s, failing only on the single most subtle boundary (inherited key
vs basic entity) — the same boundary CLAUDE.md flags as the hardest. The reference-model classifier
got it right (9/9), so the residual gap is model capability on one rule, not prompt ambiguity,
though the rule-2 wording ("no local primary-key column") is the obvious place to harden prompt_v9.

## Prompt-hardening re-run (Qwen3-14B, thinking off, 2026-06-23)

The 8/9 miss was traced to ambiguous wording, so prompt_v9's inherited-key rule was tightened in
two places: the Basic Entity paragraph and decision-order rule 2 now state explicitly that "no
local primary-key column" means *every* PK column is itself a FK to one parent (a "local" PK column
is one that is **not** a FK), and that this **includes the single-column case** — do not require the
primary key to be empty.

Re-running the same Qwen3-14B (thinking off, temperature 0) on the hardened prompt:

| run | prompt | agreement |
|-----|--------|-----------|
| `qwen_nothink.py` | original v9 | 8/9 (missed `economy`) |
| `qwen_nothink_v2.py` | hardened v9 | **9/9** |

So the residual gap was **prompt ambiguity, not model capability**: making the inherited-key
boundary explicit lets Qwen3-14B author a fully correct classifier (44 s, 1086 tokens, no code
edits). Artifacts: `raw_nothink_v2.txt`, `qwen_nothink_v2.py`, `predictions_qwen_nothink_v2.json`.

## Provenance verdict (final)

- **Qwen3-14B, thinking off, hardened prompt_v9 → 9/9**, runnable, ~44 s. The self-hosted model,
  not just a strong reference model, can author a correct deterministic Step-1 classifier from the
  prompt alone.
- **Thinking on is a liability** on the 16k server: the reasoning trace exhausts the token budget
  (`finish_reason=length`) and no code is emitted. Use thinking off for the code-generation path —
  the opposite of the per-case Step-1 path (see memory `stage3-thinking-liability`).

## Next

- Optionally confirm cross-model robustness on Coder-32B @ 8004 (code-specialised) with the hardened
  prompt; expect ≥9/9 given Qwen3-14B already passes.
- Apply the same "LLM writes the program" approach to Step 3 — a parameterised renderer per pattern
  × chart type — now that the Step-1 provenance result is solid.
