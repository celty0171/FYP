"""Classify blind Mondial column selections using Hannan/VizER ER pattern rules.

This script provides the prediction step for the deterministic baseline. It
reads only blind cases: case id, selected table, and selected columns. It does
not read expected patterns, visualisations, mappings, or reasoning.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def fk_columns(table: dict[str, Any]) -> set[str]:
    return {column for fk in table["foreign_keys"] for column in fk["columns"]}


def fk_refs_for_columns(table: dict[str, Any], columns: set[str]) -> list[str]:
    refs = []
    for fk in table["foreign_keys"]:
        if set(fk["columns"]).issubset(columns):
            refs.append(fk["references_table"])
    return refs


def classify_selection(schema: dict[str, Any], table_name: str, selected_columns: list[str]) -> dict[str, Any]:
    table = schema["tables"][table_name.lower()]
    selected = {column.lower() for column in selected_columns}
    pk = set(table["primary_key"])
    fks = fk_columns(table)
    selected_fks = selected & fks
    pk_fks = pk & fks
    pk_non_fks = pk - fks
    pk_refs = fk_refs_for_columns(table, pk_fks)

    if len(pk) >= 2 and pk and pk.issubset(fks):
        unique_refs = set(pk_refs)
        if len(unique_refs) == 1:
            pattern = "reflexive_many_many_relationship"
            reason = "The full primary key is made of foreign keys that reference the same parent table."
        else:
            pattern = "many_many_relationship"
            reason = "The full primary key is made of foreign keys to separate parent tables."
    elif pk and pk.issubset(fks) and len(set(pk_refs)) == 1:
        pattern = "basic_entity_inherited_key"
        reason = "The whole primary key is inherited as a foreign key from one parent entity."
    elif pk_fks and pk_non_fks:
        pattern = "weak_entity"
        reason = "Part of the primary key is a foreign key and part is local to the child table."
    elif selected_fks:
        selected_fk_refs = fk_refs_for_columns(table, selected_fks)
        if len(set(selected_fk_refs)) == 1:
            pattern = "one_many_relationship"
            reason = "The selection contains a foreign key that is not part of the primary key."
        else:
            pattern = "ambiguous_or_unsupported"
            reason = "The selection contains foreign keys to multiple parent entities."
    else:
        pattern = "basic_entity"
        reason = "The selection has no foreign-key dependency."

    return {
        "selected_table": table_name.lower(),
        "selected_columns": selected_columns,
        "predicted_pattern": pattern,
        "reason": reason,
        "table_primary_key": table["primary_key"],
        "table_foreign_keys": table["foreign_keys"],
    }


def normalise_cases(raw_cases: Any) -> list[dict[str, Any]]:
    if isinstance(raw_cases, list):
        cases = raw_cases
    else:
        cases = raw_cases["cases"]

    normalised = []
    for case in cases:
        if "selection" in case:
            selection = case["selection"]
            normalised.append(
                {
                    "case_id": case["case_id"],
                    "selected_table": selection["selected_table"],
                    "selected_columns": selection["selected_columns"],
                }
            )
        else:
            normalised.append(
                {
                    "case_id": case["case_id"],
                    "selected_table": case["selected_table"],
                    "selected_columns": case["selected_columns"],
                }
            )
    return normalised


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True, help="Schema summary JSON")
    parser.add_argument("--cases", required=True, help="Blind cases JSON")
    parser.add_argument("--out", required=True, help="Output JSON")
    args = parser.parse_args()

    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    cases = normalise_cases(json.loads(Path(args.cases).read_text(encoding="utf-8")))

    results = []
    for case in cases:
        result = classify_selection(schema, case["selected_table"], case["selected_columns"])
        result["case_id"] = case["case_id"]
        results.append(result)

    output = {"results": results}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} with {len(results)} classifications")


if __name__ == "__main__":
    main()
