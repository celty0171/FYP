"""Drive Qwen3-14B (port 8001) with prompt_v9 to generate a Step-1 classifier.

For each thinking mode (off / on) it: sends prompt_v9 as the user message, saves
the raw response, extracts the Python source, runs that program on the nine blind
cases, and compares its predictions to the hand-written baseline.
Pure standard library + urllib, mirroring run_pipeline.py's client.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]  # experiments/
PROMPT = (EXP / "prompts" / "prompt_v9.md").read_text(encoding="utf-8")
SCHEMA = EXP / "mondial_database" / "mondial_schema_summary_clean.json"
CASES = EXP / "inputs" / "mondial_blind_cases.json"
BASELINE = EXP / "generated" / "vizer_rule_predictions.json"

BASE_URL = "http://localhost:8001/v1"
MODEL = "Qwen3-14B"


def chat(enable_thinking: bool, max_tokens: int) -> dict:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    if not enable_thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    request = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer dummy"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=1200) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_code(text: str) -> str:
    # Drop any reasoning trace.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Prefer a fenced python block if present.
    fence = re.search(r"```(?:python)?\s*\n(.*?)```", text, flags=re.DOTALL)
    if fence:
        return fence.group(1).strip() + "\n"
    return text.strip() + "\n"


def run_classifier(code_path: Path, out_path: Path) -> dict[str, str] | None:
    proc = subprocess.run(
        [sys.executable, str(code_path), "--schema", str(SCHEMA),
         "--cases", str(CASES), "--out", str(out_path)],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        print(f"  RUN FAILED:\n{proc.stderr.strip()[:1500]}")
        return None
    results = json.loads(out_path.read_text())["results"]
    return {r["case_id"]: r["predicted_pattern"] for r in results}


def main() -> None:
    ref = {r["case_id"]: r["predicted_pattern"] for r in json.loads(BASELINE.read_text())["results"]}
    cases = {c["case_id"]: c["selected_table"] for c in json.loads(CASES.read_text())["cases"]}

    for label, thinking, max_tokens in [("nothink", False, 4096), ("think", True, 12288)]:
        print(f"\n=== Qwen3-14B  thinking={'on' if thinking else 'off'} ===")
        t0 = time.time()
        resp = chat(thinking, max_tokens)
        dt = time.time() - t0
        msg = resp["choices"][0]["message"]
        content = msg.get("content") or ""
        finish = resp["choices"][0].get("finish_reason")
        usage = resp.get("usage", {})
        print(f"  {dt:.0f}s  finish_reason={finish}  completion_tokens={usage.get('completion_tokens')}")

        (HERE / f"raw_{label}.txt").write_text(content, encoding="utf-8")
        code = extract_code(content)
        code_path = HERE / f"qwen_{label}.py"
        code_path.write_text(code, encoding="utf-8")

        preds = run_classifier(code_path, HERE / f"predictions_qwen_{label}.json")
        if preds is None:
            continue
        ok = sum(preds.get(c) == ref[c] for c in ref)
        print(f"  agreement with baseline: {ok}/{len(ref)}")
        for cid in sorted(ref, key=int):
            mark = "OK" if preds.get(cid) == ref[cid] else "DIFF"
            if mark == "DIFF":
                print(f"    case {cid} {cases[cid]}: qwen={preds.get(cid)}  ref={ref[cid]}")


if __name__ == "__main__":
    main()
