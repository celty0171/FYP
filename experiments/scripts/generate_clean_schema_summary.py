"""Generate a leakage-reduced schema summary for LLM evaluation.

The clean summary keeps enough schema evidence for pattern classification and
chart recommendation, but removes derived labels such as relationship_kind and
pre-classified scalar/text column groups.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def clean_column(column: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": column["name"],
        "type": column["type"],
        "nullable": column["nullable"],
    }


def clean_foreign_key(foreign_key: dict[str, Any]) -> dict[str, Any]:
    return {
        "columns": foreign_key["columns"],
        "references_table": foreign_key["references_table"],
        "references_columns": foreign_key["references_columns"],
    }


def clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    clean_tables = {}
    for table_name, table in schema["tables"].items():
        clean_tables[table_name] = {
            "columns": [clean_column(column) for column in table["columns"]],
            "primary_key": table["primary_key"],
            "foreign_keys": [clean_foreign_key(fk) for fk in table["foreign_keys"]],
        }
    return {"tables": clean_tables}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True, help="Full schema summary JSON")
    parser.add_argument("--out", required=True, help="Clean schema summary JSON")
    args = parser.parse_args()

    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    clean = clean_schema(schema)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} with {len(clean['tables'])} tables")


if __name__ == "__main__":
    main()
