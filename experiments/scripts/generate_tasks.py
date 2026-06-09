"""Generate LLM tasks for Mondial visualisation schema pattern experiments.

The current experiment design follows Hannan's VizER report: each task is a
DATA-FIRST user selection of one table and several columns. The model must
infer the ER schema pattern represented by the selected columns.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def collect_schema_fragment(schema: dict[str, Any], table_names: list[str]) -> dict[str, Any]:
    tables = schema["tables"]
    fragment: dict[str, Any] = {"tables": {}}
    for name in table_names:
        key = name.lower()
        if key in tables:
            fragment["tables"][key] = tables[key]
    return fragment


def build_selected_column_context(schema: dict[str, Any], table_name: str, selected_columns: list[str]) -> dict[str, Any]:
    table_key = table_name.lower()
    table = schema["tables"][table_key]
    selected = {column.lower() for column in selected_columns}

    fk_by_column: dict[str, list[dict[str, Any]]] = {}
    for fk in table["foreign_keys"]:
        for column in fk["columns"]:
            fk_by_column.setdefault(column, []).append(fk)

    columns = []
    for column in table["columns"]:
        if column["name"] not in selected:
            continue
        columns.append(
            {
                "name": column["name"],
                "type": column["type"],
                "is_primary_key": column["name"] in table["primary_key"],
                "is_foreign_key": column["name"] in fk_by_column,
                "foreign_key_references": fk_by_column.get(column["name"], []),
                "is_scalar": column["name"] in table["inferred"]["scalar_columns"],
                "is_text": column["name"] in table["inferred"]["text_columns"],
                "nullable": column["nullable"],
            }
        )

    selected_pk = [column for column in table["primary_key"] if column in selected]
    selected_fk_columns = sorted(column for column in selected if column in fk_by_column)
    pk_foreign_key_columns = [column for column in table["primary_key"] if column in fk_by_column]
    pk_local_columns = [column for column in table["primary_key"] if column not in fk_by_column]
    return {
        "selected_table": table_key,
        "selected_columns": selected_columns,
        "selected_column_metadata": columns,
        "table_primary_key": table["primary_key"],
        "selected_primary_key_columns": selected_pk,
        "selected_foreign_key_columns": selected_fk_columns,
        "primary_key_foreign_key_columns": pk_foreign_key_columns,
        "primary_key_local_columns": pk_local_columns,
        "full_primary_key_is_foreign_key": bool(table["primary_key"]) and not pk_local_columns,
        "has_compound_primary_key": len(table["primary_key"]) > 1,
        "all_table_foreign_keys": table["foreign_keys"],
        "table_inferred": table["inferred"],
    }


def make_task(case: dict[str, Any], schema_fragment: dict[str, Any], selection_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case["id"],
        "mode": case.get("mode", "data_first"),
        "task_type": "schema_pattern_identification_and_visualisation_mapping",
        "instruction": (
            "A user has selected columns from a single Mondial table. Following the "
            "VizER/Hannan ER schema-pattern rules, identify the ER visualisation schema "
            "pattern represented by this selection. Explain the schema evidence, infer "
            "cardinality constraints, recommend suitable visualisations, and produce a "
            "chart-ready mapping."
        ),
        "selection": selection_context,
        "schema_fragment": schema_fragment,
        "expected_for_evaluation": {
            "pattern": case["expected_pattern"],
            "visualisations": case["expected_visualisations"],
            "mapping": case["expected_mapping"],
            "transformations": case.get("expected_transformations", []),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True, help="Schema summary JSON")
    parser.add_argument("--patterns", required=True, help="Gold pattern cases JSON")
    parser.add_argument("--out", required=True, help="Path to write generated tasks")
    args = parser.parse_args()

    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    patterns = json.loads(Path(args.patterns).read_text(encoding="utf-8"))

    tasks = []
    for case in patterns["cases"]:
        if "selected_table" in case:
            selected_table = case["selected_table"]
            table = schema["tables"][selected_table.lower()]
            related_tables = {selected_table.lower()}
            for fk in table["foreign_keys"]:
                related_tables.add(fk["references_table"])
            fragment = collect_schema_fragment(schema, sorted(related_tables))
            selection = build_selected_column_context(
                schema,
                selected_table,
                case["selected_columns"],
            )
        else:
            fragment = collect_schema_fragment(schema, case["schema_fragment"])
            selection = {}
        tasks.append(make_task(case, fragment, selection))

    output = {
        "dataset": patterns["dataset"],
        "task_count": len(tasks),
        "tasks": tasks,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} with {len(tasks)} tasks")


if __name__ == "__main__":
    main()
