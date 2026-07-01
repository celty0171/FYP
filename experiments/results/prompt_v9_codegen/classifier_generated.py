"""Deterministic VizER ER-pattern classifier (generated from prompt_v9).

Implements the pattern-identification rules from prompt_v9: it reasons only from
the primary-key / foreign-key structure of a selection, filtered down to the
selected columns (strict scope constraint), and applies the documented decision
order. Standard library only; deterministic; reads blind input only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _lower_set(values: list[str]) -> set[str]:
    return {v.lower() for v in values}


def _foreign_key_columns(table: dict[str, Any]) -> set[str]:
    cols: set[str] = set()
    for fk in table.get("foreign_keys", []):
        cols.update(c.lower() for c in fk["columns"])
    return cols


def _selected_fk_parents(table: dict[str, Any], selected: set[str]) -> dict[str, str]:
    """Map each fully-selected foreign key (joined column name) to its parent table.

    A foreign key counts only when *all* its columns are among the selected
    columns (scope constraint): a partially-selected composite FK is ignored.
    """
    parents: dict[str, str] = {}
    for fk in table.get("foreign_keys", []):
        fk_cols = [c.lower() for c in fk["columns"]]
        if set(fk_cols).issubset(selected):
            parents["+".join(fk_cols)] = fk["references_table"].lower()
    return parents


def classify_selection(schema: dict[str, Any], table_name: str, selected_columns: list[str]) -> dict[str, Any]:
    table = schema["tables"][table_name.lower()]
    selected = _lower_set(selected_columns)

    pk = _lower_set(table.get("primary_key", []))
    fk_cols = _foreign_key_columns(table)

    # Filter keys down to the selected columns first (strict scope constraint).
    selected_pk = pk & selected
    selected_fk_cols = fk_cols & selected

    # Foreign keys (fully selected) split by whether they sit inside the PK.
    selected_fk_parents = _selected_fk_parents(table, selected)
    pk_fk_parents = {k: v for k, v in selected_fk_parents.items() if set(k.split("+")).issubset(pk)}
    non_pk_fk_parents = {k: v for k, v in selected_fk_parents.items() if not set(k.split("+")).issubset(pk)}

    pk_fk_columns = {c for key in pk_fk_parents for c in key.split("+")}
    local_pk_columns = selected_pk - pk_fk_columns
    all_pk_cols_are_fk = bool(selected_pk) and selected_pk.issubset(fk_cols)

    # Rule 1: compound PK made entirely of foreign keys -> many-many / reflexive.
    if len(selected_pk) >= 2 and all_pk_cols_are_fk:
        parents = list(pk_fk_parents.values())
        if len(set(parents)) == 1:
            pattern = "reflexive_many_many_relationship"
            reason = "The full primary key is made of foreign keys that reference the same parent table."
        else:
            pattern = "many_many_relationship"
            reason = "The full primary key is made of foreign keys to separate parent tables."

    # Rule 2: whole PK inherited as a foreign key from one parent, no local PK column.
    elif selected_pk and all_pk_cols_are_fk and len(set(pk_fk_parents.values())) == 1:
        pattern = "basic_entity_inherited_key"
        reason = "The whole primary key is inherited as a foreign key from one parent entity."

    # Rule 3: compound PK mixing foreign-key columns with local child key columns.
    elif pk_fk_columns and local_pk_columns:
        pattern = "weak_entity"
        reason = "Part of the primary key is a foreign key and part is local to the child table."

    # Rule 4: a selected foreign key that is not part of the primary key.
    elif non_pk_fk_parents:
        if len(set(non_pk_fk_parents.values())) == 1:
            pattern = "one_many_relationship"
            reason = "The selection contains a foreign key that is not part of the primary key."
        else:
            pattern = "ambiguous_or_unsupported"
            reason = "The selection contains foreign keys to multiple parent entities."

    # Rule 5: no selected foreign-key dependency.
    else:
        pattern = "basic_entity"
        reason = "The selection has no foreign-key dependency."

    return {
        "selected_table": table_name.lower(),
        "selected_columns": selected_columns,
        "predicted_pattern": pattern,
        "reason": reason,
        "table_primary_key": table.get("primary_key", []),
        "table_foreign_keys": table.get("foreign_keys", []),
    }


def _normalise_cases(raw: Any) -> list[dict[str, Any]]:
    cases = raw["cases"] if isinstance(raw, dict) else raw
    out = []
    for case in cases:
        if "selection" in case:
            sel = case["selection"]
            out.append({
                "case_id": case["case_id"],
                "selected_table": sel["selected_table"],
                "selected_columns": sel["selected_columns"],
            })
        else:
            out.append({
                "case_id": case["case_id"],
                "selected_table": case["selected_table"],
                "selected_columns": case["selected_columns"],
            })
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify blind selections into VizER ER patterns.")
    parser.add_argument("--schema", required=True, help="Schema summary JSON")
    parser.add_argument("--cases", required=True, help="Blind cases JSON")
    parser.add_argument("--out", required=True, help="Output JSON")
    args = parser.parse_args()

    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    cases = _normalise_cases(json.loads(Path(args.cases).read_text(encoding="utf-8")))

    results = []
    for case in cases:
        result = classify_selection(schema, case["selected_table"], case["selected_columns"])
        result["case_id"] = case["case_id"]
        results.append(result)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} with {len(results)} classifications")


if __name__ == "__main__":
    main()
