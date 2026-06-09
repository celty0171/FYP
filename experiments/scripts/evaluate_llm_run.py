"""Evaluate a directory of LLM schema-pattern responses."""

from __future__ import annotations

import argparse
import glob
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


VISUALISATION_ALIASES = {
    "sankey": "sankey_diagram",
    "sankey_chart": "sankey_diagram",
    "scatter": "scatter_chart",
    "scatter_plot": "scatter_chart",
    "scatter_diagram": "scatter_chart",
    "bubble": "bubble_chart",
    "bar": "bar_chart",
    "line": "line_chart",
    "stacked_bar": "stacked_bar_chart",
    "grouped_bar": "grouped_bar_chart",
    "tree_map": "treemap",
    "hierarchy": "hierarchy_tree",
    "tree": "hierarchy_tree",
    "network": "network_chart",
    "chord": "chord_diagram",
    "circle_pack": "circle_packing",
}


def normalise_label(value: Any) -> str:
    label = str(value).strip().lower()
    label = re.sub(r"[^a-z0-9]+", "_", label).strip("_")
    return VISUALISATION_ALIASES.get(label, label)


def as_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(item).lower() for item in value}
    return {str(value).lower()}


def load_response(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "response" in data and isinstance(data["response"], dict):
        response = data["response"]
        response.setdefault("case_id", data.get("case_id"))
        return response
    return data


def gold_for_case(case_id: str, gold_cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {case["id"]: case for case in gold_cases}
    if case_id in by_id:
        return by_id[case_id]
    if case_id.isdigit():
        index = int(case_id) - 1
        if 0 <= index < len(gold_cases):
            return gold_cases[index]
    raise KeyError(f"Cannot match response case_id {case_id!r} to a gold case")


def foreign_key_columns(table: dict[str, Any]) -> set[str]:
    return {column for fk in table["foreign_keys"] for column in fk["columns"]}


def expected_schema_evidence(table: dict[str, Any], selected_columns: list[str]) -> dict[str, Any]:
    selected = set(selected_columns)
    primary_key = set(table["primary_key"])
    fk_columns = foreign_key_columns(table)
    selected_fk = selected & fk_columns
    fk_in_pk = selected_fk & primary_key
    fk_not_in_pk = selected_fk - primary_key
    local_pk = primary_key - fk_columns
    return {
        "primary_key_columns": set(table["primary_key"]),
        "foreign_key_columns": selected_fk,
        "selected_foreign_key_columns": selected_fk,
        "foreign_keys_in_primary_key": fk_in_pk,
        "foreign_keys_not_in_primary_key": fk_not_in_pk,
        "local_primary_key_columns": local_pk,
        "primary_key_is_compound": len(primary_key) > 1,
        "all_primary_key_columns_are_foreign_keys": bool(primary_key) and primary_key.issubset(fk_columns),
    }


def evaluate_schema_evidence(response: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    evidence = response.get("schema_evidence", {})
    checks = {}
    for key, expected_value in expected.items():
        actual_value = evidence.get(key)
        if isinstance(expected_value, set):
            checks[key] = as_set(actual_value) == {str(item).lower() for item in expected_value}
        else:
            checks[key] = actual_value == expected_value
    return {
        "checks": checks,
        "all_match": all(checks.values()) if checks else False,
        "mismatched_fields": [key for key, passed in checks.items() if not passed],
    }


def evaluate_response(response: dict[str, Any], gold_case: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    expected_pattern = normalise_label(gold_case["expected_pattern"])
    actual_pattern = normalise_label(response.get("identified_pattern", ""))
    expected_visualisations = {normalise_label(v) for v in gold_case.get("expected_visualisations", [])}
    actual_visualisations = {normalise_label(v) for v in response.get("recommended_visualisations", [])}

    table = schema["tables"][gold_case["selected_table"]]
    schema_evidence = evaluate_schema_evidence(
        response,
        expected_schema_evidence(table, gold_case["selected_columns"]),
    )

    return {
        "case_id": str(response.get("case_id")),
        "gold_case_id": gold_case["id"],
        "selected_table": gold_case["selected_table"],
        "expected_pattern": expected_pattern,
        "actual_pattern": actual_pattern,
        "pattern_match": actual_pattern == expected_pattern,
        "expected_visualisations": sorted(expected_visualisations),
        "actual_visualisations": sorted(actual_visualisations),
        "visualisation_overlap": sorted(expected_visualisations & actual_visualisations),
        "missing_expected_visualisations": sorted(expected_visualisations - actual_visualisations),
        "unexpected_visualisations": sorted(actual_visualisations - expected_visualisations),
        "schema_evidence": schema_evidence,
        "confidence": response.get("confidence"),
    }


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(results)
    pattern_matches = sum(1 for result in results if result["pattern_match"])
    evidence_matches = sum(1 for result in results if result["schema_evidence"]["all_match"])
    visualisation_any_overlap = sum(1 for result in results if result["visualisation_overlap"])
    exact_visualisation_sets = sum(
        1
        for result in results
        if set(result["expected_visualisations"]) == set(result["actual_visualisations"])
    )
    pattern_confusions = Counter(
        f"{result['expected_pattern']} -> {result['actual_pattern']}"
        for result in results
        if not result["pattern_match"]
    )
    return {
        "case_count": count,
        "pattern_matches": pattern_matches,
        "pattern_accuracy": pattern_matches / count if count else 0,
        "schema_evidence_matches": evidence_matches,
        "schema_evidence_accuracy": evidence_matches / count if count else 0,
        "visualisation_any_overlap": visualisation_any_overlap,
        "visualisation_overlap_rate": visualisation_any_overlap / count if count else 0,
        "exact_visualisation_set_matches": exact_visualisation_sets,
        "exact_visualisation_set_rate": exact_visualisation_sets / count if count else 0,
        "pattern_confusions": dict(pattern_confusions),
    }


def write_markdown(path: Path, run_id: str, summary: dict[str, Any], results: list[dict[str, Any]]) -> None:
    lines = [
        f"# LLM Run Evaluation: {run_id}",
        "",
        "## Summary",
        "",
        f"- Pattern accuracy: {summary['pattern_matches']}/{summary['case_count']} ({summary['pattern_accuracy']:.1%})",
        f"- Schema evidence accuracy: {summary['schema_evidence_matches']}/{summary['case_count']} ({summary['schema_evidence_accuracy']:.1%})",
        f"- Visualisation overlap: {summary['visualisation_any_overlap']}/{summary['case_count']} ({summary['visualisation_overlap_rate']:.1%})",
        f"- Exact visualisation set match: {summary['exact_visualisation_set_matches']}/{summary['case_count']} ({summary['exact_visualisation_set_rate']:.1%})",
        "",
        "## Cases",
        "",
        "| Case | Table | Expected | Actual | Pattern | Viz overlap | Evidence |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        lines.append(
            "| {case_id} | {table} | {expected} | {actual} | {pattern} | {overlap} | {evidence} |".format(
                case_id=result["case_id"],
                table=result["selected_table"],
                expected=result["expected_pattern"],
                actual=result["actual_pattern"],
                pattern="yes" if result["pattern_match"] else "no",
                overlap=", ".join(result["visualisation_overlap"]) or "-",
                evidence="yes" if result["schema_evidence"]["all_match"] else "no",
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, help="Directory containing metadata.json and responses/")
    parser.add_argument("--gold", required=True, help="Gold pattern JSON")
    parser.add_argument("--schema", required=True, help="Clean schema summary JSON")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    metadata_path = run_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))["cases"]
    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))

    responses = []
    for filename in sorted(glob.glob(str(run_dir / "responses" / "*.json"))):
        responses.append(load_response(Path(filename)))

    results = [evaluate_response(response, gold_for_case(str(response["case_id"]), gold), schema) for response in responses]
    summary = build_summary(results)
    output = {"metadata": metadata, "summary": summary, "results": results}

    (run_dir / "evaluation.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown(run_dir / "summary.md", metadata.get("run_id", run_dir.name), summary, results)
    print(
        f"Wrote evaluation for {summary['case_count']} cases: "
        f"{summary['pattern_matches']}/{summary['case_count']} pattern matches"
    )


if __name__ == "__main__":
    main()
