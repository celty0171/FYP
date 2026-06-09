"""Evaluate deterministic VizER baseline predictions against gold cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_results(predictions: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(predictions, list):
        return predictions
    return predictions["results"]


def gold_case_for_prediction(prediction: dict[str, Any], gold_cases: list[dict[str, Any]]) -> dict[str, Any]:
    case_id = str(prediction["case_id"])
    by_original_id = {case["id"]: case for case in gold_cases}
    if case_id in by_original_id:
        return by_original_id[case_id]

    if case_id.isdigit():
        index = int(case_id) - 1
        if 0 <= index < len(gold_cases):
            return gold_cases[index]

    raise KeyError(f"Cannot match prediction case_id {case_id!r} to a gold case")


def evaluate(predictions: list[dict[str, Any]], gold_cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for prediction in predictions:
        gold_case = gold_case_for_prediction(prediction, gold_cases)
        expected_pattern = gold_case["expected_pattern"]
        predicted_pattern = prediction["predicted_pattern"]
        results.append(
            {
                **prediction,
                "gold_case_id": gold_case["id"],
                "expected_pattern": expected_pattern,
                "matches_expected": predicted_pattern == expected_pattern,
            }
        )

    return {
        "results": results,
        "summary": {
            "case_count": len(results),
            "matches": sum(1 for result in results if result["matches_expected"]),
            "all_match": all(result["matches_expected"] for result in results),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True, help="Baseline prediction JSON")
    parser.add_argument("--gold", required=True, help="Gold cases JSON")
    parser.add_argument("--out", required=True, help="Evaluation output JSON")
    args = parser.parse_args()

    predictions = load_results(json.loads(Path(args.predictions).read_text(encoding="utf-8")))
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    output = evaluate(predictions, gold["cases"])

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(
        f"Wrote {out_path} with {output['summary']['matches']}/"
        f"{output['summary']['case_count']} matches"
    )


if __name__ == "__main__":
    main()
