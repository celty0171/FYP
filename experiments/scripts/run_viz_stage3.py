"""Stage-3-only visualisation runner for controlled model comparisons.

Unlike run_pipeline.py (which always re-runs Stage 1+2 with the same model), this
script feeds a *fixed*, already-validated Stage 1+2 mapping to the model so the
only thing being measured is Stage 3 visualisation-implementation ability.

It reuses the LLM client, prompt rendering, row projection and HTML extraction
from run_pipeline.py so behaviour stays consistent with the main pipeline.

Example:

    python experiments/scripts/run_viz_stage3.py \
        --mapping experiments/results/prompt_v8_thinking/responses/case_8.json \
        --data experiments/mondial_database/mondial_data.json \
        --table encompasses --columns country continent percentage \
        --library d3 \
        --model Qwen3-14B --base-url http://localhost:8001/v1 --enable-thinking \
        --out experiments/results/viz_case8/qwen3_14b_d3
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import run_pipeline as rp

REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else REPO_ROOT / path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mapping", required=True, help="Fixed Stage 1+2 response JSON (the validated mapping)")
    parser.add_argument("--data", required=True, help="Mondial data JSON in {'tables': {...}} shape")
    parser.add_argument("--table", required=True, help="Selected table name")
    parser.add_argument("--columns", nargs="+", required=True, help="Selected columns")
    parser.add_argument("--impl-prompt", default="experiments/prompts/visualisation_implementation_prompt.md")
    parser.add_argument("--library", default="d3")
    parser.add_argument("--data-filter", default="")
    parser.add_argument("--max-rows", type=int, default=500)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--impl-max-tokens", type=int, default=8192)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument(
        "--compact-data",
        action="store_true",
        help="Inline the data as compact (non-indented) JSON to save context tokens; "
        "needed when thinking + verbose data overflow a small context window.",
    )
    parser.add_argument("--out", required=True, help="Output directory for this single generation")
    args = parser.parse_args()

    pattern_result = json.loads(resolve(args.mapping).read_text(encoding="utf-8"))
    data = json.loads(resolve(args.data).read_text(encoding="utf-8"))

    case = {"case_id": str(pattern_result.get("case_id", "case")), "selected_table": args.table, "selected_columns": args.columns}

    out_dir = resolve(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    raw = None
    rows = rp.table_rows(data, args.table, args.columns, args.max_rows)
    prompt = rp.render(
        resolve(args.impl_prompt).read_text(encoding="utf-8"),
        {
            "TARGET_LIBRARY": args.library,
            "PATTERN_AND_MAPPING_RESULT": json.dumps(rp.compact_mapping(pattern_result), indent=2),
            "DATA": json.dumps(rows, separators=(",", ":")) if args.compact_data else json.dumps(rows, indent=2),
            "DATA_FILTER": args.data_filter,
        },
    )
    raw = rp.chat(
        [{"role": "user", "content": prompt}],
        model=args.model,
        base_url=args.base_url,
        temperature=args.temperature,
        max_tokens=args.impl_max_tokens,
        timeout=args.timeout,
        enable_thinking=args.enable_thinking,
    )
    html = rp.extract_html(raw)
    seconds = round(time.monotonic() - started, 1)

    (out_dir / "case.html").write_text(html, encoding="utf-8")
    (out_dir / "raw.txt").write_text(raw, encoding="utf-8")
    (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    (out_dir / "metadata.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "model": args.model,
                "base_url": args.base_url,
                "library": args.library,
                "enable_thinking": args.enable_thinking,
                "temperature": args.temperature,
                "impl_max_tokens": args.impl_max_tokens,
                "mapping_source": str(args.mapping),
                "table": args.table,
                "columns": args.columns,
                "rows_used": len(rows),
                "data_filter": args.data_filter,
                "seconds": seconds,
                "html_bytes": len(html),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[{args.model} / {args.library}] {len(html)} bytes html in {seconds}s -> {out_dir}")


if __name__ == "__main__":
    main()
