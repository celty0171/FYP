import argparse
import json
import sys
from typing import Any, Dict, List, Set, Tuple

ALLOWED_PATTERNS = {
    "basic_entity",
    "basic_entity_inherited_key",
    "weak_entity",
    "one_many_relationship",
    "many_many_relationship",
    "reflexive_many_many_relationship",
    "ambiguous_or_unsupported",
}


def _norm_name(value: Any) -> str:
    return str(value).strip().lower()


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    tables = schema.get("tables", {})
    norm_tables: Dict[str, Any] = {}

    for tname_raw, tdef in tables.items():
        tname = _norm_name(tname_raw)

        cols = tdef.get("columns", [])
        col_names = []
        for c in cols:
            cname = c.get("name") if isinstance(c, dict) else c
            if cname is not None:
                col_names.append(_norm_name(cname))

        pk = [_norm_name(c) for c in tdef.get("primary_key", [])]

        fks = []
        for fk in tdef.get("foreign_keys", []):
            fk_cols = [_norm_name(c) for c in fk.get("columns", [])]
            ref_table = _norm_name(fk.get("references_table", ""))
            ref_cols = [_norm_name(c) for c in fk.get("references_columns", [])]
            fks.append(
                {
                    "columns": fk_cols,
                    "references_table": ref_table,
                    "references_columns": ref_cols,
                }
            )

        norm_tables[tname] = {
            "columns": col_names,
            "primary_key": pk,
            "foreign_keys": fks,
        }

    return {"tables": norm_tables}


def _extract_cases(cases_json: Any) -> List[Dict[str, Any]]:
    if isinstance(cases_json, dict) and "cases" in cases_json:
        raw_cases = cases_json.get("cases", [])
    elif isinstance(cases_json, list):
        raw_cases = cases_json
    else:
        raise ValueError("Cases JSON must be a list or an object with key 'cases'.")

    out = []
    for idx, c in enumerate(raw_cases):
        if not isinstance(c, dict):
            raise ValueError(f"Case at index {idx} is not an object.")

        selection = c.get("selection", {}) if isinstance(c.get("selection", {}), dict) else {}
        case_id = c.get("case_id", idx)

        selected_table = c.get("selected_table", selection.get("selected_table"))
        selected_columns = c.get("selected_columns", selection.get("selected_columns", []))

        if selected_table is None:
            raise ValueError(f"Case {case_id} missing selected_table.")
        if selected_columns is None:
            selected_columns = []

        out.append(
            {
                "case_id": case_id,
                "selected_table": selected_table,
                "selected_columns": selected_columns,
            }
        )
    return out


def _fk_col_to_parents_filtered_by_selection(
    table_def: Dict[str, Any],
    selected_cols: Set[str],
) -> Dict[str, Set[str]]:
    """
    Build mapping from selected FK column -> referenced parent tables.
    Only FK constraints whose all columns are selected are considered.
    """
    mapping: Dict[str, Set[str]] = {}
    for fk in table_def.get("foreign_keys", []):
        fk_cols = fk.get("columns", [])
        fk_col_set = set(fk_cols)
        if not fk_col_set:
            continue
        if not fk_col_set.issubset(selected_cols):
            continue  # strict scope: ignore FK if any FK column is unselected
        parent = _norm_name(fk.get("references_table", ""))
        for col in fk_cols:
            mapping.setdefault(col, set()).add(parent)
    return mapping


def classify_selection(schema: Dict[str, Any], table_name: str, selected_columns: List[str]) -> Dict[str, str]:
    nschema = _normalize_schema(schema)
    tables = nschema.get("tables", {})

    tname = _norm_name(table_name)
    if tname not in tables:
        return {
            "predicted_pattern": "ambiguous_or_unsupported",
            "reason": f"table '{table_name}' not found in schema",
        }

    table_def = tables[tname]

    selected_cols: Set[str] = {_norm_name(c) for c in selected_columns}
    pk_all: List[str] = table_def.get("primary_key", [])
    pk_set: Set[str] = set(pk_all)

    # Filter PK and FK strictly to selected columns
    selected_pk_cols = [c for c in pk_all if c in selected_cols]
    selected_pk_set = set(selected_pk_cols)

    fk_col_to_parents = _fk_col_to_parents_filtered_by_selection(table_def, selected_cols)
    selected_fk_cols: Set[str] = set(fk_col_to_parents.keys())

    # Helper sets over selected PK columns
    pk_fk_cols = selected_pk_set & selected_fk_cols
    pk_local_cols = selected_pk_set - selected_fk_cols

    # Rule 1: full table PK has >=2 cols and every PK col is a selected FK
    # (strict scope implies each PK col must be selected and FK recognized)
    if len(pk_all) >= 2 and set(pk_all).issubset(selected_cols) and set(pk_all).issubset(selected_fk_cols):
        parent_tables = set()
        for c in pk_all:
            parent_tables.update(fk_col_to_parents.get(c, set()))

        if len(parent_tables) == 1:
            return {
                "predicted_pattern": "reflexive_many_many_relationship",
                "reason": "full primary key has at least two columns, all are selected foreign keys, and they reference one parent table",
            }
        elif len(parent_tables) >= 2:
            return {
                "predicted_pattern": "many_many_relationship",
                "reason": "full primary key has at least two columns and all are selected foreign keys referencing multiple parent tables",
            }
        else:
            return {
                "predicted_pattern": "ambiguous_or_unsupported",
                "reason": "primary-key columns are selected but parent references are unresolved for many-many decision",
            }

    # Rule 2: every PK column is selected FK and all reference same parent (includes single-column PK)
    if len(pk_all) >= 1 and set(pk_all).issubset(selected_cols) and set(pk_all).issubset(selected_fk_cols):
        parent_tables = set()
        for c in pk_all:
            parent_tables.update(fk_col_to_parents.get(c, set()))
        if len(parent_tables) == 1:
            return {
                "predicted_pattern": "basic_entity_inherited_key",
                "reason": "every primary-key column is a selected foreign key to a single parent and no local primary-key column exists",
            }

    # Rule 3: PK is compound and has both FK PK cols and local PK cols (selected view)
    # Apply only when all PK cols are selected so compound status is knowable under strict scope.
    if len(pk_all) >= 2 and set(pk_all).issubset(selected_cols):
        if len(pk_fk_cols) >= 1 and len(pk_local_cols) >= 1:
            return {
                "predicted_pattern": "weak_entity",
                "reason": "compound primary key contains both selected foreign-key columns and local primary-key columns",
            }

    # Rule 4: selected non-PK FK(s)
    non_pk_fk_cols = selected_fk_cols - pk_set
    if non_pk_fk_cols:
        parent_tables = set()
        for c in non_pk_fk_cols:
            parent_tables.update(fk_col_to_parents.get(c, set()))
        if len(parent_tables) == 1:
            return {
                "predicted_pattern": "one_many_relationship",
                "reason": "selected columns include foreign key(s) not in primary key and they reference a single parent table",
            }
        else:
            return {
                "predicted_pattern": "ambiguous_or_unsupported",
                "reason": "selected non-primary-key foreign keys reference multiple parent tables",
            }

    # Rule 5: default
    return {
        "predicted_pattern": "basic_entity",
        "reason": "no selected non-primary-key foreign key and no selected-key structure matching inherited, weak, or many-many patterns",
    }


def _run_cli(schema_path: str, cases_path: str, out_path: str) -> None:
    schema = _load_json(schema_path)
    cases_json = _load_json(cases_path)
    cases = _extract_cases(cases_json)

    results = []
    for c in cases:
        case_id = c["case_id"]
        selected_table = c["selected_table"]
        selected_columns = c["selected_columns"]

        pred = classify_selection(schema, selected_table, selected_columns)
        pattern = pred.get("predicted_pattern", "ambiguous_or_unsupported")
        reason = pred.get("reason", "")

        if pattern not in ALLOWED_PATTERNS:
            pattern = "ambiguous_or_unsupported"
            reason = (reason + "; " if reason else "") + "predicted pattern outside allowed set"

        results.append(
            {
                "case_id": case_id,
                "selected_table": selected_table,
                "selected_columns": selected_columns,
                "predicted_pattern": pattern,
                "reason": reason,
            }
        )

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"results": results}, f, indent=2, ensure_ascii=False)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Classify ER pattern from schema and blind cases.")
    parser.add_argument("--schema", required=True, help="Path to schema JSON file")
    parser.add_argument("--cases", required=True, help="Path to blind cases JSON file")
    parser.add_argument("--out", required=True, help="Path to output JSON file")
    args = parser.parse_args(argv)

    try:
        _run_cli(args.schema, args.cases, args.out)
        return 0
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
