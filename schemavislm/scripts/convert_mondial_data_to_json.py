"""Convert Mondial INSERT statements into grouped JSON rows."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


INSERT_RE = re.compile(
    r"^\s*INSERT\s+INTO\s+(?P<table>[A-Za-z_][A-Za-z0-9_]*)\s+VALUES\s*\((?P<values>.*)\);\s*$",
    re.IGNORECASE,
)


def parse_sql_values(text: str) -> list[Any]:
    values: list[Any] = []
    current: list[str] = []
    in_string = False
    token_is_string = False
    i = 0

    while i < len(text):
        char = text[i]
        if in_string:
            if char == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    current.append("'")
                    i += 2
                    continue
                in_string = False
            else:
                current.append(char)
            i += 1
            continue

        if char == "'":
            in_string = True
            token_is_string = True
            i += 1
            continue

        if char == ",":
            values.append(convert_token("".join(current).strip(), token_is_string))
            current = []
            token_is_string = False
            i += 1
            continue

        current.append(char)
        i += 1

    if in_string:
        raise ValueError(f"Unterminated SQL string in values: {text[:120]}")

    values.append(convert_token("".join(current).strip(), token_is_string))
    return values


def convert_token(token: str, token_is_string: bool) -> Any:
    if token_is_string:
        return token
    if token.upper() == "NULL":
        return None
    if token == "":
        return ""
    try:
        if re.fullmatch(r"[+-]?\d+", token):
            return int(token)
        return float(token)
    except ValueError:
        return token


def table_columns(schema: dict[str, Any]) -> dict[str, list[str]]:
    return {
        table_name: [column["name"] for column in table["columns"]]
        for table_name, table in schema["tables"].items()
    }


def convert_data(sql_text: str, schema: dict[str, Any]) -> dict[str, Any]:
    columns_by_table = table_columns(schema)
    tables: dict[str, list[dict[str, Any]]] = {table_name: [] for table_name in columns_by_table}
    skipped_lines: list[dict[str, Any]] = []

    for line_number, line in enumerate(sql_text.splitlines(), start=1):
        match = INSERT_RE.match(line)
        if not match:
            continue

        table_name = match.group("table").lower()
        values = parse_sql_values(match.group("values"))
        columns = columns_by_table.get(table_name)
        if columns is None:
            skipped_lines.append(
                {
                    "line": line_number,
                    "table": table_name,
                    "reason": "table not present in schema summary",
                }
            )
            continue

        if len(values) != len(columns):
            raise ValueError(
                f"Line {line_number}: table {table_name} has {len(columns)} columns "
                f"but INSERT has {len(values)} values"
            )

        tables[table_name].append(dict(zip(columns, values)))

    table_counts = {table_name: len(rows) for table_name, rows in tables.items() if rows}
    return {
        "tables": {table_name: rows for table_name, rows in tables.items() if rows},
        "table_counts": table_counts,
        "skipped_lines": skipped_lines,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Path to mondial_data.sql")
    parser.add_argument("--schema", required=True, help="Clean schema summary JSON")
    parser.add_argument("--out", required=True, help="Path to write grouped data JSON")
    parser.add_argument("--table", help="Optional table name to export as a row array")
    args = parser.parse_args()

    data_path = Path(args.data)
    schema_path = Path(args.schema)
    out_path = Path(args.out)

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    converted = convert_data(data_path.read_text(encoding="utf-8", errors="replace"), schema)

    output: Any = converted
    if args.table:
        table_name = args.table.lower()
        output = converted["tables"].get(table_name, [])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.table:
        print(f"Wrote {out_path} with {len(output)} rows from table {args.table.lower()}")
    else:
        print(
            f"Wrote {out_path} with {sum(converted['table_counts'].values())} rows "
            f"across {len(converted['table_counts'])} tables"
        )


if __name__ == "__main__":
    main()
