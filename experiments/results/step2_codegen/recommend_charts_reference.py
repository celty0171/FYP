"""Deterministic Step-2 chart recommender + mapping generator (D3 pipeline).

Reference implementation of the program elicited by
prompts/step2_chart_mapping_prompt.md. Given the schema, a column selection and its
Step-1 pattern, it classifies each selected attribute's dimension type from its SQL
type, checks each chart in the pattern's group against its mandatory requirements,
and emits, for each eligible chart, a mapping whose field names match exactly what
the Step-3 renderers consume. Standard library only; deterministic; blind input only.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SCALAR_TYPES = ("INT", "INTEGER", "BIGINT", "SMALLINT", "NUMERIC", "DECIMAL",
                "FLOAT", "DOUBLE", "REAL", "MONEY")
TEMPORAL_TYPES = ("DATE", "TIME", "TIMESTAMP", "YEAR")
TEXT_TYPES = ("VARCHAR", "CHAR", "TEXT")


def _dim_type(sql_type: str | None) -> str:
    t = (sql_type or "").upper()
    if any(t.startswith(p) or p in t for p in TEMPORAL_TYPES):
        # Guard: TIMESTAMP contains no scalar prefix clash; check temporal first.
        for p in TEMPORAL_TYPES:
            if t.startswith(p):
                return "temporal"
    if any(t.startswith(p) for p in SCALAR_TYPES):
        return "scalar"
    if any(t.startswith(p) for p in TEXT_TYPES):
        return "discrete"
    return "discrete"


def _columns(schema: dict[str, Any], table: str) -> dict[str, str]:
    return {c["name"].lower(): c.get("type") for c in schema["tables"][table]["columns"]}


def _fk_map(schema: dict[str, Any], table: str) -> dict[str, str]:
    """Map each foreign-key column (lower) to its referenced parent table (lower)."""
    out: dict[str, str] = {}
    for fk in schema["tables"][table].get("foreign_keys", []):
        for col in fk["columns"]:
            out[col.lower()] = fk["references_table"].lower()
    return out


def recommend(schema: dict[str, Any], table_name: str, selected_columns: list[str], pattern: str) -> dict[str, Any]:
    table = table_name.lower()
    sel = [c.lower() for c in selected_columns]
    coltypes = _columns(schema, table)
    pk = {c.lower() for c in schema["tables"][table].get("primary_key", [])}
    fkmap = _fk_map(schema, table)

    dims = {c: _dim_type(coltypes.get(c)) for c in sel}
    # scalar attributes = selected scalar columns that are not keys/foreign keys (selection order)
    scalar_attrs = [c for c in sel if dims[c] == "scalar" and c not in pk and c not in fkmap]
    temporal_attrs = [c for c in sel if dims[c] == "temporal" and c not in pk and c not in fkmap]
    discrete_attrs = [c for c in sel if dims[c] == "discrete" and c not in pk and c not in fkmap]
    sel_pk = [c for c in sel if c in pk]
    sel_pk_fks = [c for c in sel if c in pk and c in fkmap]
    sel_nonpk_fks = [c for c in sel if c in fkmap and c not in pk]
    local_pk = [c for c in sel_pk if c not in fkmap]

    candidates: list[dict[str, Any]] = []

    def add(chart: str, eligible: Any, reason: str, mapping: dict[str, Any] | None = None, note: str | None = None) -> None:
        entry = {"chart": chart, "eligible": eligible, "reason": reason, "mapping": mapping or {}}
        if note:
            entry["note"] = note
        candidates.append(entry)

    if pattern in ("basic_entity", "basic_entity_inherited_key"):
        key = sel_pk[0] if sel_pk else (sel_pk_fks[0] if sel_pk_fks else (sel[0] if sel else None))
        add("bar chart", bool(key and len(scalar_attrs) >= 1),
            "needs a key and >=1 scalar attribute",
            {"table": table, "key": key, "measure": scalar_attrs[0]} if (key and scalar_attrs) else None)
        add("scatter diagram", bool(key and len(scalar_attrs) >= 2),
            "needs a key and >=2 scalar attributes",
            {"table": table, "key": key, "x": scalar_attrs[0], "y": scalar_attrs[1]} if (key and len(scalar_attrs) >= 2) else None)
        add("bubble chart", bool(key and len(scalar_attrs) >= 3),
            "needs a key and >=3 scalar attributes",
            {"table": table, "key": key, "x": scalar_attrs[0], "y": scalar_attrs[1], "size": scalar_attrs[2]} if (key and len(scalar_attrs) >= 3) else None)
        add("calendar chart", bool(key and len(temporal_attrs) >= 1),
            "needs a key and >=1 temporal attribute",
            {"table": table, "date": temporal_attrs[0], "key": key} if (key and temporal_attrs) else None)
        add("choropleth map", "conditional" if (key and scalar_attrs) else False,
            "conditional: needs key to be geographical + a scalar attribute",
            {"table": table, "region": key, "color": scalar_attrs[0]} if (key and scalar_attrs) else None,
            note="assert only if the key is a geographical region code")
        add("word cloud", "conditional" if (key and scalar_attrs) else False,
            "conditional: needs key to be lexical + a scalar attribute",
            {"table": table, "text": key, "size": scalar_attrs[0]} if (key and scalar_attrs) else None,
            note="assert only if the key is words/labels")

    elif pattern == "one_many_relationship":
        parent = sel_nonpk_fks[0] if sel_nonpk_fks else None
        child = local_pk[0] if local_pk else (sel_pk[0] if sel_pk else None)
        a1 = scalar_attrs[0] if scalar_attrs else None
        add("tree map", bool(parent and child and a1),
            "needs parent FK, child key, and a scalar attribute",
            {"table": table, "parent": parent, "child": child, "measure": a1} if (parent and child and a1) else None)
        add("circle packing", bool(parent and child and a1),
            "needs parent FK, child key, and a scalar attribute",
            {"table": table, "parent": parent, "child": child, "measure": a1} if (parent and child and a1) else None)
        add("hierarchy tree", bool(parent and child),
            "needs parent FK and child key (no scalar required)",
            {"table": table, "parent": parent, "child": child} if (parent and child) else None)

    elif pattern in ("many_many_relationship", "reflexive_many_many_relationship"):
        # Schema-only sibling of the data-driven selector (proposal v2 §4); this reference
        # takes no data rows, so it applies the documented rows-None fallback: node-link
        # (Sankey/chord) only when a scalar width exists, matrix/force always (count fallback),
        # arc reflexive-only. Density/N/symmetric ranking lives in gpt_recommend_charts.py.
        is_reflexive = pattern == "reflexive_many_many_relationship"
        src = sel_pk_fks[0] if len(sel_pk_fks) >= 1 else None
        tgt = sel_pk_fks[1] if len(sel_pk_fks) >= 2 else None
        width = scalar_attrs[0] if scalar_attrs else None
        category = discrete_attrs[0] if discrete_attrs else None
        have_edges = bool(src and tgt)
        value = width if width else "count"

        matrix_map = {"table": table, "source": src, "target": tgt, "value": value, "pattern": pattern}
        if category:
            matrix_map["category"] = category
        add("matrix heatmap", have_edges,
            "needs the two primary-key foreign keys; cell value = scalar attribute or edge count",
            matrix_map if have_edges else None)
        add("force graph", have_edges,
            "needs the two primary-key foreign keys; links weighted by scalar attribute or edge count",
            {"table": table, "source": src, "target": tgt, "value": value, "pattern": pattern} if have_edges else None)
        add("Sankey diagram", bool(have_edges and width),
            "needs the two primary-key foreign keys and a scalar relationship attribute",
            {"table": table, "source": src, "target": tgt, "width": width, "pattern": pattern} if (have_edges and width) else None)
        add("chord diagram", bool(have_edges and width),
            "needs the two primary-key foreign keys and a scalar relationship attribute",
            {"table": table, "source": src, "target": tgt, "width": width, "pattern": pattern} if (have_edges and width) else None)
        add("arc diagram", bool(have_edges and is_reflexive),
            "reflexive-only: needs the two primary-key foreign keys of a reflexive relationship",
            {"table": table, "source": src, "target": tgt, "value": value, "pattern": pattern} if (have_edges and is_reflexive) else None)

    elif pattern == "weak_entity":
        k1 = sel_pk_fks[0] if sel_pk_fks else None
        k2 = local_pk[0] if local_pk else None
        a1 = scalar_attrs[0] if scalar_attrs else None
        add("line chart", bool(k1 and k2 and a1 and dims.get(k2) == "scalar"),
            "needs scalar child key k2 (x) and scalar a1 (y)",
            {"table": table, "series": k1, "x": k2, "y": a1} if (k1 and k2 and a1) else None)
        add("stacked bar chart", bool(k1 and k2 and a1),
            "needs scalar a1 (best with k2 complete across k1)",
            {"table": table, "group": k1, "segment": k2, "value": a1} if (k1 and k2 and a1) else None)
        add("grouped bar chart", bool(k1 and k2 and a1),
            "needs scalar a1",
            {"table": table, "group": k1, "segment": k2, "value": a1} if (k1 and k2 and a1) else None)
        add("spider chart", bool(k1 and k2 and a1),
            "needs scalar a1 (best with k2 complete across k1)",
            {"table": table, "ring": k1, "spoke": k2, "value": a1} if (k1 and k2 and a1) else None)

    # Optional colour channel (paper Section 3): a spare DISCRETE attribute -> colour key,
    # else a spare SCALAR/temporal attribute -> colour spectrum. Schema-derivable, so applied
    # here too (the row-dependent cardinality caps / spider>=3 gate live in gpt_recommend_charts).
    def pick_color(used):
        for d in discrete_attrs:
            if d not in used:
                return (d, "discrete")
        for s in scalar_attrs + temporal_attrs:
            if s not in used:
                return (s, "scalar")
        return None

    _colour_charts = {"scatter diagram", "bubble chart", "word cloud", "tree map",
                      "circle packing", "Sankey diagram", "chord diagram"}
    for c in candidates:
        if not (c["eligible"] and c["mapping"]):
            continue
        used = {str(v).lower() for v in c["mapping"].values() if v}
        if c["chart"] == "hierarchy tree":
            pc = next(((d, "discrete") for d in discrete_attrs if d not in used), None)  # discrete lines only
        elif c["chart"] in _colour_charts:
            pc = pick_color(used)
        else:
            pc = None
        if pc:
            c["mapping"]["color"], c["mapping"]["color_type"] = pc

    recommended = [c["chart"] for c in candidates if c["eligible"] is True]
    # selected = the eligible chart whose mapping uses the most of the selection.
    eligible_full = [c for c in candidates if c["eligible"] is True]
    selected: dict[str, Any] = {}
    if eligible_full:
        best = max(eligible_full, key=lambda c: len([v for v in c["mapping"].values() if v]))
        selected = {"chart": best["chart"], "mapping": best["mapping"]}

    return {
        "selected_table": table,
        "selected_columns": selected_columns,
        "identified_pattern": pattern,
        "dimension_types": dims,
        "recommended_charts": recommended,
        "candidates": candidates,
        "selected": selected,
    }


def _normalise_cases(raw: Any) -> list[dict[str, Any]]:
    cases = raw["cases"] if isinstance(raw, dict) else raw
    out = []
    for case in cases:
        sel = case.get("selection", case)
        out.append({
            "case_id": case["case_id"],
            "selected_table": sel["selected_table"],
            "selected_columns": sel["selected_columns"],
            "identified_pattern": case.get("identified_pattern") or case.get("predicted_pattern"),
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Step-2 chart recommendation + Step-3 mapping generation.")
    parser.add_argument("--schema", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    cases = _normalise_cases(json.loads(Path(args.cases).read_text(encoding="utf-8")))

    results = []
    for case in cases:
        res = recommend(schema, case["selected_table"], case["selected_columns"], case["identified_pattern"])
        res["case_id"] = case["case_id"]
        results.append(res)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} with {len(results)} recommendations")


if __name__ == "__main__":
    main()
