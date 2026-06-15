"""End-to-end ER-pattern -> visualisation pipeline driven by a self-hosted LLM.

This runs the three experiment stages against a vLLM OpenAI-compatible endpoint
(e.g. the HPC Qwen models reached over an SSH tunnel on localhost):

    Stage 1+2  pattern identification + chart selection/mapping
               (prompts/mondial_pattern_prompt.md)
    Stage 3    runnable visualisation implementation as standalone HTML
               (prompts/visualisation_implementation_prompt.md)

For each case it writes, under the run directory:

    responses/case_<id>.json        parsed stage-1+2 result (scorable by
                                    scripts/evaluate_llm_run.py)
    raw/case_<id>.pattern.txt       raw model text for stage 1+2
    raw/case_<id>.impl.txt          raw model text for stage 3
    visualisations/case_<id>.html   generated visualisation
    metadata.json                   run metadata
    pipeline_summary.json           per-case outcome + timing

The layout (metadata.json + responses/) matches evaluate_llm_run.py, so a run
can be scored directly:

    python experiments/scripts/evaluate_llm_run.py \
        --run-dir experiments/results/<run_id> \
        --gold experiments/inputs/mondial_gold_patterns.json \
        --schema experiments/mondial_database/mondial_schema_summary_clean.json

Pure standard library: the LLM is called via urllib, no external packages.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from classify_vizer_pattern import classify_selection  # deterministic PK/FK rule baseline

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = {
    "schema": "experiments/mondial_database/mondial_schema_summary_clean.json",
    "cases": "experiments/inputs/mondial_blind_cases.json",
    "data": "experiments/mondial_database/mondial_data.json",
    "pattern_prompt": "experiments/prompts/mondial_pattern_prompt.md",
    "impl_prompt": "experiments/prompts/visualisation_implementation_prompt.md",
}


# --------------------------------------------------------------------------- #
# LLM client (OpenAI-compatible chat completions over urllib)
# --------------------------------------------------------------------------- #
def chat(
    messages: list[dict[str, str]],
    *,
    model: str,
    base_url: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    enable_thinking: bool,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # Qwen3 emits <think> traces by default; disabling keeps JSON/code clean.
    if not enable_thinking and "qwen3" in model.lower():
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    try:
        body = _post(payload, base_url, timeout)
    except urllib.error.URLError as exc:
        message = str(exc)
        input_match = re.search(r"has (\d+) input tokens", message)
        ctx_match = re.search(r"maximum context length is (\d+)", message)
        # vLLM rejects when input + max_tokens > context; refit to what remains.
        if "too large" in message and input_match and ctx_match:
            remaining = int(ctx_match.group(1)) - int(input_match.group(1)) - 64
            if remaining < 256:
                raise urllib.error.URLError(
                    f"Input too long ({input_match.group(1)} tokens) for this model's context; "
                    f"reduce --max-rows or shorten the prompt. Original: {message}"
                ) from exc
            payload["max_tokens"] = remaining
            body = _post(payload, base_url, timeout)
        else:
            raise
    return body["choices"][0]["message"]["content"]


def _post(payload: dict[str, Any], base_url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer dummy"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise urllib.error.URLError(f"HTTP {exc.code} from {exc.url}: {detail}") from exc


# --------------------------------------------------------------------------- #
# Response parsing
# --------------------------------------------------------------------------- #
def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def first_balanced_span(text: str, open_ch: str, close_ch: str) -> str | None:
    """Return the first top-level {...} / [...] span, ignoring braces in strings."""
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == open_ch:
            depth += 1
        elif char == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def extract_json(text: str) -> dict[str, Any]:
    cleaned = strip_thinking(text)
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    span = first_balanced_span(cleaned, "{", "}")
    if span is None:
        raise ValueError("No JSON object found in model response")
    return json.loads(span)


def extract_html(text: str) -> str:
    cleaned = strip_thinking(text)
    fenced = re.search(r"```(?:html)?\s*(.*?)```", cleaned, flags=re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    lowered = cleaned.lower()
    for marker in ("<!doctype html", "<html"):
        idx = lowered.find(marker)
        if idx != -1:
            return cleaned[idx:].strip()
    return cleaned


# --------------------------------------------------------------------------- #
# Prompt / context construction
# --------------------------------------------------------------------------- #
def render(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def schema_fragment(schema: dict[str, Any], table_name: str) -> dict[str, Any]:
    """The selected table plus the parent tables its foreign keys reference."""
    tables = schema["tables"]
    key = table_name.lower()
    wanted = {key}
    for fk in tables[key]["foreign_keys"]:
        wanted.add(fk["references_table"].lower())
    return {"tables": {name: tables[name] for name in sorted(wanted) if name in tables}}


def selection_context(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(case["case_id"]),
        "selected_table": case["selected_table"].lower(),
        "selected_columns": case["selected_columns"],
    }


def table_rows(data: dict[str, Any], table_name: str, columns: list[str], max_rows: int) -> list[dict[str, Any]]:
    rows = data["tables"].get(table_name.lower(), [])
    projected = [{column: row.get(column) for column in columns} for row in rows]
    return projected[:max_rows] if max_rows > 0 else projected


# --------------------------------------------------------------------------- #
# Stages
# --------------------------------------------------------------------------- #
def run_pattern_stage(case, schema, pattern_template, *, args, given_pattern: str | None = None) -> tuple[str, dict[str, Any]]:
    values = {
        "SELECTION": json.dumps(selection_context(case), indent=2),
        "SCHEMA_FRAGMENT": json.dumps(schema_fragment(schema, case["selected_table"]), indent=2),
    }
    if given_pattern is not None:
        values["GIVEN_PATTERN"] = given_pattern
    prompt = render(pattern_template, values)
    raw = chat(
        [{"role": "user", "content": prompt}],
        model=args.model,
        base_url=args.base_url,
        temperature=args.temperature,
        max_tokens=args.pattern_max_tokens,
        timeout=args.timeout,
        enable_thinking=args.enable_thinking,
    )
    result = extract_json(raw)
    result["case_id"] = str(case["case_id"])  # never trust the model for the id
    if given_pattern is not None:
        # Hybrid: the deterministic rule owns the label; the LLM only does evidence + mapping.
        result["identified_pattern"] = given_pattern
    return raw, result


def compact_mapping(pattern_result: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields stage 3 needs, to leave context room for the HTML."""
    keep = (
        "case_id",
        "identified_pattern",
        "recommended_visualisations",
        "selected_visualisation",
        "chart_mapping",
    )
    compact = {key: pattern_result[key] for key in keep if pattern_result.get(key)}
    return compact or pattern_result


def run_impl_stage(case, pattern_result, data, impl_template, *, args) -> str:
    rows = table_rows(data, case["selected_table"], case["selected_columns"], args.max_rows)
    prompt = render(
        impl_template,
        {
            "TARGET_LIBRARY": args.library,
            "PATTERN_AND_MAPPING_RESULT": json.dumps(compact_mapping(pattern_result), indent=2),
            "DATA": json.dumps(rows, indent=2),
            "DATA_FILTER": args.data_filter,
        },
    )
    raw = chat(
        [{"role": "user", "content": prompt}],
        model=args.model,
        base_url=args.base_url,
        temperature=args.temperature,
        max_tokens=args.impl_max_tokens,
        timeout=args.timeout,
        enable_thinking=args.enable_thinking,
    )
    return extract_html(raw)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def resolve(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else REPO_ROOT / path


def load_cases(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = raw["cases"] if isinstance(raw, dict) else raw
    normalised = []
    for case in cases:
        if "selection" in case:
            selection = case["selection"]
            normalised.append(
                {
                    "case_id": case.get("case_id", case.get("id")),
                    "selected_table": selection["selected_table"],
                    "selected_columns": selection["selected_columns"],
                }
            )
        else:
            normalised.append(
                {
                    "case_id": case.get("case_id", case.get("id")),
                    "selected_table": case["selected_table"],
                    "selected_columns": case["selected_columns"],
                }
            )
    return normalised


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--schema", default=DEFAULTS["schema"])
    parser.add_argument("--cases", default=DEFAULTS["cases"])
    parser.add_argument("--data", default=DEFAULTS["data"])
    parser.add_argument("--pattern-prompt", default=DEFAULTS["pattern_prompt"])
    parser.add_argument("--impl-prompt", default=DEFAULTS["impl_prompt"])
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Assign the pattern deterministically (classify_vizer_pattern) and let the LLM only "
        "do schema evidence + visualisation mapping; uses --hybrid-prompt.",
    )
    parser.add_argument(
        "--hybrid-prompt",
        default="experiments/prompts/mondial_pattern_prompt_mcbrien_hybrid.md",
        help="Prompt template (with a {{GIVEN_PATTERN}} placeholder) used in --hybrid mode.",
    )
    parser.add_argument("--out-dir", default=None, help="Run directory (default experiments/results/<run-id>)")
    parser.add_argument("--run-id", default=None, help="Run label (default pipeline_<model>)")
    parser.add_argument("--case-id", default=None, help="Run a single case id only")
    parser.add_argument("--model", default="Qwen3-14B")
    parser.add_argument("--base-url", default="http://localhost:8001/v1")
    parser.add_argument("--library", default="d3", help="Target viz library, e.g. d3 / google_charts / vega_lite")
    parser.add_argument("--data-filter", default="", help="Optional natural-language data filter for stage 3")
    parser.add_argument("--max-rows", type=int, default=500, help="Cap rows passed to stage 3 (0 = all)")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--pattern-max-tokens", type=int, default=4096)
    parser.add_argument("--impl-max-tokens", type=int, default=8192)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--enable-thinking", action="store_true", help="Keep Qwen3 <think> reasoning on")
    parser.add_argument("--skip-impl", action="store_true", help="Run stage 1+2 only (no visualisation)")
    args = parser.parse_args()

    schema = json.loads(resolve(args.schema).read_text(encoding="utf-8"))
    prompt_path = args.hybrid_prompt if args.hybrid else args.pattern_prompt
    pattern_template = resolve(prompt_path).read_text(encoding="utf-8")
    impl_template = resolve(args.impl_prompt).read_text(encoding="utf-8")
    data = json.loads(resolve(args.data).read_text(encoding="utf-8")) if not args.skip_impl else {}
    cases = load_cases(resolve(args.cases))
    if args.case_id is not None:
        cases = [case for case in cases if str(case["case_id"]) == str(args.case_id)]
        if not cases:
            raise SystemExit(f"No case with id {args.case_id!r} in {args.cases}")

    run_id = args.run_id or f"pipeline_{re.sub(r'[^A-Za-z0-9._-]+', '_', args.model)}"
    run_dir = resolve(args.out_dir) if args.out_dir else REPO_ROOT / "experiments" / "results" / run_id
    (run_dir / "responses").mkdir(parents=True, exist_ok=True)
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)
    if not args.skip_impl:
        (run_dir / "visualisations").mkdir(parents=True, exist_ok=True)

    summary: list[dict[str, Any]] = []
    for case in cases:
        cid = str(case["case_id"])
        record: dict[str, Any] = {"case_id": cid, "selected_table": case["selected_table"]}
        started = time.monotonic()
        try:
            given_pattern = None
            if args.hybrid:
                given_pattern = classify_selection(
                    schema, case["selected_table"], case["selected_columns"]
                )["predicted_pattern"]
                record["deterministic_pattern"] = given_pattern
            raw_pattern, pattern_result = run_pattern_stage(
                case, schema, pattern_template, args=args, given_pattern=given_pattern
            )
            (run_dir / "raw" / f"case_{cid}.pattern.txt").write_text(raw_pattern, encoding="utf-8")
            (run_dir / "responses" / f"case_{cid}.json").write_text(
                json.dumps(pattern_result, indent=2), encoding="utf-8"
            )
            record["identified_pattern"] = pattern_result.get("identified_pattern")
            record["recommended_visualisations"] = pattern_result.get("recommended_visualisations")
            record["pattern_ok"] = True
        except (urllib.error.URLError, ValueError, json.JSONDecodeError, KeyError, TimeoutError) as exc:
            record["pattern_ok"] = False
            record["error"] = f"stage1+2: {type(exc).__name__}: {exc}"
            summary.append(record)
            print(f"[case {cid}] FAILED stage 1+2: {record['error']}")
            continue

        if not args.skip_impl:
            try:
                total_rows = len(data["tables"].get(case["selected_table"].lower(), []))
                used_rows = total_rows if args.max_rows <= 0 else min(total_rows, args.max_rows)
                record["rows_total"] = total_rows
                record["rows_used"] = used_rows
                if used_rows < total_rows:
                    print(f"[case {cid}] note: data truncated to {used_rows}/{total_rows} rows for stage 3")
                html = run_impl_stage(case, pattern_result, data, impl_template, args=args)
                (run_dir / "visualisations" / f"case_{cid}.html").write_text(html, encoding="utf-8")
                record["impl_ok"] = True
                record["html_bytes"] = len(html)
            except (urllib.error.URLError, ValueError, KeyError, TimeoutError) as exc:
                record["impl_ok"] = False
                record["error"] = f"stage3: {type(exc).__name__}: {exc}"

        record["seconds"] = round(time.monotonic() - started, 1)
        summary.append(record)
        print(
            f"[case {cid}] {case['selected_table']}: pattern="
            f"{record.get('identified_pattern')} viz={record.get('recommended_visualisations')} "
            f"({record['seconds']}s)"
        )

    metadata = {
        "run_id": run_id,
        "model": args.model,
        "base_url": args.base_url,
        "library": args.library,
        "temperature": args.temperature,
        "enable_thinking": args.enable_thinking,
        "skip_impl": args.skip_impl,
        "hybrid": args.hybrid,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "schema_file": args.schema,
        "cases_file": args.cases,
        "pattern_prompt_file": prompt_path,
        "impl_prompt_file": args.impl_prompt,
        "case_count": len(cases),
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (run_dir / "pipeline_summary.json").write_text(
        json.dumps({"metadata": metadata, "cases": summary}, indent=2), encoding="utf-8"
    )

    ok = sum(1 for r in summary if r.get("pattern_ok"))
    print(f"\nWrote run to {run_dir}")
    print(f"Stage 1+2 succeeded for {ok}/{len(summary)} cases.")
    if not args.skip_impl:
        viz = sum(1 for r in summary if r.get("impl_ok"))
        print(f"Stage 3 produced HTML for {viz}/{len(summary)} cases.")


if __name__ == "__main__":
    main()
