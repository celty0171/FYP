You are an expert researcher in relational databases, ER-model reasoning, and schema-driven visualisation recommendation, specialising in identifying conceptual visualisation schema patterns from Mondial database column selections.

Your task is to write a deterministic Python program that implements the ER pattern-identification rules below, so that the rules can be applied to any selection by running code rather than by reasoning case by case. Reason only from the primary-key (PK) and foreign-key (FK) structure of a selection, never from the natural-language meaning of table or column names, and encode exactly that reasoning into the program.

# 1. The rules the program must implement

## Scope constraint (strict)

Pattern identification uses only the selected table and the selected columns. A foreign key counts only if its column is one of the selected columns; a foreign key whose column is not in the selected columns must be ignored entirely and must play no part in the decision. Likewise, a primary-key column counts only if it is selected. In other words, the program must first filter the table's keys down to the selected columns, then apply the rules to that filtered set. It must never introduce a column the user did not select.

Concretely, the set of relevant foreign-key columns is the intersection of the table's foreign-key columns with the selected columns. If none of the selected columns is a foreign key, the selection cannot be `one_many_relationship`, `weak_entity`, `many_many_relationship`, or `reflexive_many_many_relationship` on the basis of an unselected foreign key.

## Pattern rules

### Basic Entity
A selected table is a basic entity when the selected columns contain a primary key and attributes without a selected foreign-key dependency.

We also classify an inherited-key table as a basic entity (`basic_entity_inherited_key`) when the whole primary key is inherited as a foreign key from one parent entity, with no local primary-key column. Here "no local primary-key column" means **every** primary-key column is itself a foreign key to that one parent — *not* that the table has no primary key. This holds even when the primary key is a single column: a one-column primary key that is itself a foreign key to one parent is `basic_entity_inherited_key`, not `basic_entity`. (A "local" primary-key column is a primary-key column that is **not** a foreign key.)

### Weak Entity
A weak entity has a compound primary key where a proper subset of the key is a foreign key to a single parent entity and at least one remaining primary-key column is local to the child entity. Boundary: if every primary-key column is also a foreign key, the table is inherited-key basic; if the primary key combines foreign-key columns with local child key columns, the table is weak.

### One-Many Relationship
A one-many pattern is identified when the selected columns contain a foreign key to a single parent entity, and that foreign key is not part of the table's primary key.

### Many-Many Relationship
A many-many relationship is represented by a relationship table whose primary key is composed of two foreign keys to two separate parent tables.

### Reflexive Many-Many Relationship
A reflexive many-many relationship is a special many-many case where both foreign keys reference the same parent table.

## Decision order

Apply the first matching rule:

1. If the full table primary key has at least two columns and every primary-key column is a foreign key, classify as `many_many_relationship` when the foreign keys reference different parent tables, or `reflexive_many_many_relationship` when they reference the same parent table.
2. Else if every primary-key column is itself a foreign key and they all reference the same single parent entity (so there is no non-foreign-key primary-key column), classify as `basic_entity_inherited_key`. This includes the single-column case: a one-column primary key that is a foreign key to one parent matches this rule. Do not require the primary key to be empty.
3. Else if the table primary key is compound and contains both foreign-key columns and local primary-key columns, classify as `weak_entity`.
4. Else if the selected columns include a foreign key that is not part of the table primary key, classify as `one_many_relationship` (when the selected non-PK foreign keys reference a single parent) or `ambiguous_or_unsupported` (when they reference more than one parent).
5. Else classify as `basic_entity`.

## Boundary checks the program must respect

- Do not classify a weak entity as `one_many_relationship` merely because it has a parent foreign key: if that foreign key is part of the table primary key and there is also a local primary-key column, the pattern is `weak_entity`.
- Do not classify a selection as `basic_entity` merely because the table has its own primary key and scalar attributes: if a selected foreign key is not part of the primary key, the pattern is `one_many_relationship`.
- For two-foreign-key primary keys, check whether the two keys reference the same parent (reflexive) or different parents (plain many-many).

# 2. Input data shapes the program must read

Schema summary JSON (the `--schema` file). Top level is `{"tables": { ... }}`. Keys are lower-case table names. Each table is:

```json
{
  "columns": [{"name": "country", "nullable": false, "type": "VARCHAR(4)"}],
  "primary_key": ["country", "continent"],
  "foreign_keys": [
    {"columns": ["country"], "references_table": "country", "references_columns": []},
    {"columns": ["continent"], "references_table": "continent", "references_columns": []}
  ]
}
```

Blind cases JSON (the `--cases` file). Either a list of cases or `{"cases": [ ... ]}`. Each case carries `case_id`, `selected_table`, and `selected_columns` (the program should also tolerate a case that nests these under a `"selection"` object). The cases file contains **no** expected patterns, visualisations, or reasoning, and the program must not read any gold/answer file — prediction must depend only on blind input.

# 3. Required program interface (contract)

Write a single self-contained Python module, standard library only, deterministic (no randomness, no network, no model calls). It must:

- Expose a function `classify_selection(schema, table_name, selected_columns) -> dict` that returns at least `predicted_pattern` (one of `basic_entity`, `basic_entity_inherited_key`, `weak_entity`, `one_many_relationship`, `many_many_relationship`, `reflexive_many_many_relationship`, `ambiguous_or_unsupported`) and a short `reason`.
- Be case-insensitive on table and column names (the schema keys and columns are lower-case).
- Provide a CLI `--schema <file> --cases <file> --out <file>` that classifies every case and writes `{"results": [ ... ]}`, where each result object contains `case_id`, `selected_table`, `selected_columns`, `predicted_pattern`, and `reason`.

# 4. Output

Return the complete Python source for the module and nothing else — no prose, no explanation, no markdown fences around extra commentary. The code must run as-is under `python3 <module>.py --schema ... --cases ... --out ...`.
