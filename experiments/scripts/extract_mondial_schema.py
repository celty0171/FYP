"""Extract a compact schema summary from the Mondial SQL schema.

The goal is not to implement a complete SQL parser. Mondial's schema file is
regular enough that a conservative parser is sufficient for experiment setup.
The output is designed to be fed into LLM prompts for schema-pattern matching.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SQL_TYPE_RE = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+"
    r"(?P<type>[A-Za-z]+(?:\s*\([^)]+\))?)(?P<rest>.*)$",
    re.IGNORECASE,
)


def normalise_identifier(value: str) -> str:
    return value.strip().strip('"').lower()


def split_top_level_csv(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(char)
    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def remove_sql_comments(sql: str) -> str:
    cleaned_lines = []
    for line in sql.splitlines():
        cleaned_lines.append(line.split("--", 1)[0])
    return "\n".join(cleaned_lines)


def parse_column_definition(item: str) -> dict[str, Any] | None:
    match = SQL_TYPE_RE.match(item.strip())
    if not match:
        return None
    rest = match.group("rest").upper()
    return {
        "name": normalise_identifier(match.group("name")),
        "type": " ".join(match.group("type").split()).upper(),
        "nullable": "NOT NULL" not in rest and "PRIMARY KEY" not in rest,
        "primary_key_inline": "PRIMARY KEY" in rest,
        "unique_inline": "UNIQUE" in rest,
        "foreign_key_inline": "REFERENCES" in rest,
        "raw": item.strip(),
    }


def parse_column_list(text: str) -> list[str]:
    return [normalise_identifier(part) for part in text.split(",") if part.strip()]


def parse_table_body(body: str) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    columns: list[dict[str, Any]] = []
    primary_key: list[str] = []
    foreign_keys: list[dict[str, Any]] = []

    for item in split_top_level_csv(body):
        compact = " ".join(item.split())
        upper = compact.upper()
        starts_like_constraint = upper.startswith("CONSTRAINT ") or upper.startswith("PRIMARY KEY")
        if starts_like_constraint and "PRIMARY KEY" in upper:
            match = re.search(r"PRIMARY\s+KEY\s*\(([^)]+)\)", compact, re.IGNORECASE)
            if match:
                primary_key = parse_column_list(match.group(1))
            continue
        if starts_like_constraint and "FOREIGN KEY" in upper:
            match = re.search(
                r"FOREIGN\s+KEY\s*\(([^)]+)\)\s+REFERENCES\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(([^)]+)\))?",
                compact,
                re.IGNORECASE,
            )
            if match:
                foreign_keys.append(
                    {
                        "columns": parse_column_list(match.group(1)),
                        "references_table": normalise_identifier(match.group(2)),
                        "references_columns": parse_column_list(match.group(3) or ""),
                        "raw": compact,
                    }
                )
            continue
        if starts_like_constraint:
            continue

        column = parse_column_definition(compact)
        if column:
            if column["primary_key_inline"]:
                primary_key.append(column["name"])
            inline_fk = re.search(r"REFERENCES\s+([A-Za-z_][A-Za-z0-9_]*)", compact, re.IGNORECASE)
            if inline_fk:
                foreign_keys.append(
                    {
                        "columns": [column["name"]],
                        "references_table": normalise_identifier(inline_fk.group(1)),
                        "references_columns": [],
                        "raw": compact,
                    }
                )
            columns.append(column)

    return columns, primary_key, foreign_keys


def parse_schema(sql: str) -> dict[str, Any]:
    sql = remove_sql_comments(sql)
    table_re = re.compile(
        r"CREATE\s+TABLE\s+(?:public\.)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<body>.*?)\);",
        re.IGNORECASE | re.DOTALL,
    )

    tables: dict[str, Any] = {}
    for match in table_re.finditer(sql):
        table_name = normalise_identifier(match.group("name"))
        columns, primary_key, foreign_keys = parse_table_body(match.group("body"))
        tables[table_name] = {
            "columns": columns,
            "primary_key": primary_key,
            "foreign_keys": foreign_keys,
        }

    infer_relationship_kinds(tables)
    return {"tables": tables}


def infer_relationship_kinds(tables: dict[str, Any]) -> None:
    add_implied_mondial_foreign_keys(tables)

    for table_name, table in tables.items():
        pk = set(table["primary_key"])
        fk_cols = {col for fk in table["foreign_keys"] for col in fk["columns"]}
        pk_fks = pk & fk_cols
        pk_local = pk - fk_cols

        if len(table["foreign_keys"]) >= 2 and fk_cols and fk_cols.issubset(pk):
            relationship_kind = "relationship_table_candidate"
        elif pk and pk.issubset(fk_cols):
            relationship_kind = "inherited_key_entity_candidate"
        elif pk_fks and pk_local:
            relationship_kind = "weak_entity_candidate"
        elif table["foreign_keys"]:
            relationship_kind = "entity_with_foreign_key"
        else:
            relationship_kind = "entity"

        scalar_columns = [
            col["name"]
            for col in table["columns"]
            if any(token in col["type"] for token in ["INT", "NUMERIC", "DECIMAL", "DATE"])
        ]
        text_columns = [
            col["name"]
            for col in table["columns"]
            if any(token in col["type"] for token in ["CHAR", "TEXT", "VARCHAR"])
        ]

        table["inferred"] = {
            "relationship_kind": relationship_kind,
            "scalar_columns": scalar_columns,
            "text_columns": text_columns,
            "nullable_columns": [col["name"] for col in table["columns"] if col["nullable"]],
        }


def add_implied_mondial_foreign_keys(tables: dict[str, Any]) -> None:
    """Add FK hints that are present conceptually but absent/commented in SQL.

    The provided Mondial schema contains some commented-out foreign keys. For
    LLM experiments we want the schema summary to expose the conceptual links
    that are used in the McBrien and Poulovassilis examples.
    """

    def table_has_fk(table: dict[str, Any], columns: list[str], ref_table: str) -> bool:
        return any(
            fk["columns"] == columns and fk["references_table"] == ref_table
            for fk in table["foreign_keys"]
        )

    def add_fk(table_name: str, columns: list[str], ref_table: str, ref_columns: list[str]) -> None:
        if table_name not in tables or ref_table not in tables:
            return
        table = tables[table_name]
        if not table_has_fk(table, columns, ref_table):
            table["foreign_keys"].append(
                {
                    "columns": columns,
                    "references_table": ref_table,
                    "references_columns": ref_columns,
                    "raw": "inferred from Mondial conceptual schema",
                    "inferred": True,
                }
            )

    add_fk("country_population", ["country"], "country", ["code"])
    add_fk("population", ["country"], "country", ["code"])
    add_fk("economy", ["country"], "country", ["code"])
    add_fk("politics", ["country"], "country", ["code"])
    add_fk("spoken", ["country"], "country", ["code"])
    add_fk("ethnic_group", ["country"], "country", ["code"])
    add_fk("religion", ["country"], "country", ["code"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True, help="Path to mondial_schema.sql")
    parser.add_argument("--out", required=True, help="Path to write JSON summary")
    args = parser.parse_args()

    schema_path = Path(args.schema)
    output_path = Path(args.out)
    summary = parse_schema(schema_path.read_text(encoding="utf-8", errors="replace"))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {output_path} with {len(summary['tables'])} tables")


if __name__ == "__main__":
    main()
