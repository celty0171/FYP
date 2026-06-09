"""Lightweight scorer for JSON LLM responses against Mondial gold cases.

This is intentionally simple: it checks the fields that can be scored reliably
without semantic judgement. Use the rubric for the qualitative part.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def normalise(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def score_response(response: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    expected_pattern = normalise(expected["pattern"])
    actual_pattern = normalise(response.get("identified_pattern", ""))

    expected_visualisations = {normalise(v) for v in expected.get("visualisations", [])}
    actual_visualisations = {
        normalise(v) for v in response.get("recommended_visualisations", [])
    }

    expected_transformations = {normalise(v) for v in expected.get("transformations", [])}
    actual_transformations = {normalise(v) for v in response.get("required_transformations", [])}

    return {
        "pattern_match": actual_pattern == expected_pattern,
        "visualisation_overlap": sorted(expected_visualisations & actual_visualisations),
        "missing_expected_visualisations": sorted(expected_visualisations - actual_visualisations),
        "transformation_match": expected_transformations.issubset(actual_transformations),
        "expected_pattern": expected_pattern,
        "actual_pattern": actual_pattern,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, help="One generated task JSON file")
    parser.add_argument("--response", required=True, help="LLM response JSON file")
    parser.add_argument("--out", required=True, help="Score output JSON")
    args = parser.parse_args()

    task = json.loads(Path(args.task).read_text(encoding="utf-8"))
    response = json.loads(Path(args.response).read_text(encoding="utf-8"))
    score = score_response(response, task["expected_for_evaluation"])

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(score, indent=2), encoding="utf-8")
    print(json.dumps(score, indent=2))


if __name__ == "__main__":
    main()

