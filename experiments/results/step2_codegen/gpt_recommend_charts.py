import argparse
import json
from copy import deepcopy

NEAR_COMPLETE = 0.6

# Relationship-selector thresholds (proposal v2 §4). A relationship is drawn as a
# node-link view (Sankey/chord) only while it is sparse and small; once it is dense
# OR large the matrix heatmap is preferred (node-link becomes a hairball).
DENSE = 0.10          # density = |edges| / (|E1| * |E2|)
LARGE_N = 200         # size of the larger node set
SYMMETRIC_MIN = 0.6   # share of mutual (a,b)/(b,a) pairs to call a reflexive relation symmetric

NUMERIC_TYPES = {
    "INT", "INTEGER", "BIGINT", "SMALLINT", "NUMERIC", "DECIMAL",
    "FLOAT", "DOUBLE", "REAL", "MONEY"
}
TEMPORAL_TYPES = {"DATE", "TIME", "TIMESTAMP", "YEAR"}
TEXT_TYPES = {"VARCHAR", "CHAR", "TEXT"}


def norm_name(x):
    return x.lower() if isinstance(x, str) else x


def base_sql_type(type_str):
    if not isinstance(type_str, str):
        return ""
    return type_str.strip().upper().split("(")[0].strip()


def dimension_type(sql_type):
    b = base_sql_type(sql_type)
    if b in NUMERIC_TYPES:
        return "scalar"
    if b in TEMPORAL_TYPES:
        return "temporal"
    if b in TEXT_TYPES:
        return "discrete"
    return "other"


def as_cases_list(cases_obj):
    if isinstance(cases_obj, dict) and "cases" in cases_obj and isinstance(cases_obj["cases"], list):
        return cases_obj["cases"]
    if isinstance(cases_obj, list):
        return cases_obj
    return []


def normalize_schema(schema):
    out = {"tables": {}}
    tables = schema.get("tables", {}) if isinstance(schema, dict) else {}
    for tname, tdef in tables.items():
        tname_n = norm_name(tname)
        cols = tdef.get("columns", [])
        pk = [norm_name(c) for c in tdef.get("primary_key", [])]
        fks = tdef.get("foreign_keys", [])
        col_map = {}
        for c in cols:
            cn = norm_name(c.get("name"))
            if cn is None:
                continue
            col_map[cn] = {
                "name": c.get("name"),
                "name_norm": cn,
                "type": c.get("type", ""),
                "dim": dimension_type(c.get("type", "")),
            }
        fk_norm = []
        for fk in fks:
            fk_cols = [norm_name(c) for c in fk.get("columns", [])]
            fk_norm.append({
                "columns": fk_cols,
                "references_table": norm_name(fk.get("references_table")),
            })
        out["tables"][tname_n] = {
            "name": tname,
            "name_norm": tname_n,
            "columns": cols,
            "columns_by_name": col_map,
            "primary_key": pk,
            "foreign_keys": fk_norm,
        }
    return out


def fk_column_map(table_def):
    m = {}
    for fk in table_def.get("foreign_keys", []):
        for c in fk.get("columns", []):
            m[c] = fk.get("references_table")
    return m


def selected_column_meta(table_def, selected_columns):
    cols_meta = []
    pk_set = set(table_def.get("primary_key", []))
    fk_map = fk_column_map(table_def)
    col_defs = table_def.get("columns_by_name", {})
    for c in selected_columns:
        cn = norm_name(c)
        cdef = col_defs.get(cn, {"name": c, "name_norm": cn, "type": "", "dim": "other"})
        cols_meta.append({
            "name": cdef.get("name", c),
            "name_norm": cn,
            "type": cdef.get("type", ""),
            "dim": cdef.get("dim", "other"),
            "is_pk": cn in pk_set,
            "is_fk": cn in fk_map,
            "fk_parent": fk_map.get(cn),
        })
    return cols_meta


def first(cols, pred):
    for c in cols:
        if pred(c):
            return c
    return None


def all_where(cols, pred):
    return [c for c in cols if pred(c)]


def weak_completeness(rows, k1, k2):
    if rows is None:
        return None
    k1n = norm_name(k1)
    k2n = norm_name(k2)
    K1 = set()
    K2 = set()
    P = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        rr = {norm_name(k): v for k, v in r.items()}
        v1 = rr.get(k1n)
        v2 = rr.get(k2n)
        if v1 is not None:
            K1.add(v1)
        if v2 is not None:
            K2.add(v2)
        if v1 is not None and v2 is not None:
            P.add((v1, v2))
    if len(K1) == 0 or len(K2) == 0:
        return {"complete": False, "density": 0.0, "k1_count": len(K1), "k2_count": len(K2), "pairs": len(P)}
    density = len(P) / (len(K1) * len(K2))
    return {
        "complete": density >= NEAR_COMPLETE,
        "density": density,
        "k1_count": len(K1),
        "k2_count": len(K2),
        "pairs": len(P),
    }


def relationship_signals(rows, source, target, is_reflexive):
    """Measure the deterministic data signals the relationship selector needs (proposal v2 §4).

    Returns None when no data is supplied (so the caller falls back to schema-only ranking).
    density = |distinct edges| / (|E1| * |E2|); N = size of the larger node set; symmetric
    (reflexive only) = share of pairs whose reverse (b,a) also occurs.
    """
    if rows is None:
        return None
    sn, tn = norm_name(source), norm_name(target)
    S, T, pairs = set(), set(), set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        rr = {norm_name(k): v for k, v in r.items()}
        a, b = rr.get(sn), rr.get(tn)
        if a is not None:
            S.add(a)
        if b is not None:
            T.add(b)
        if a is not None and b is not None:
            pairs.add((a, b))
    if is_reflexive:
        nodes = S | T
        N = len(nodes)
        denom = N * N
    else:
        N = max(len(S), len(T))
        denom = len(S) * len(T)
    density = (len(pairs) / denom) if denom else 0.0
    symmetric = None
    if is_reflexive and pairs:
        mutual = sum(1 for (a, b) in pairs if (b, a) in pairs)
        symmetric = mutual / len(pairs)
    return {
        "density": density,
        "N": N,
        "edges": len(pairs),
        "symmetric": symmetric,
        "source_n": len(S),
        "target_n": len(T),
    }


def rank_relationship_charts(sig, has_scalar, has_categorical, is_reflexive):
    """Ordered list of recommended charts for a relationship, per proposal v2 §4.

    node-link (Sankey/chord) only while sparse & small & has_scalar; otherwise the
    matrix leads. arc diagram is reflexive-only. Charts not in the returned list are
    reported as not-recommended (eligible False) by the caller.
    """
    dense = sig is not None and sig["density"] >= DENSE
    large = sig is not None and sig["N"] >= LARGE_N
    node_link = (["chord diagram", "Sankey diagram"] if is_reflexive
                 else ["Sankey diagram", "chord diagram"]) if has_scalar else []
    arc = ["arc diagram"] if is_reflexive else []

    if has_scalar and not (dense or large):
        # sparse & small & scalar -> node-link reads best; force + arc as extra views.
        return node_link + ["force graph"] + arc
    if dense or large:
        # dense OR large -> matrix leads (node-link would be a hairball), but still
        # offer node-link ranked after force whenever it is renderable (has a scalar).
        return ["matrix heatmap", "force graph"] + node_link + arc
    if not has_scalar and has_categorical:
        # no scalar width but a categorical edge attribute -> matrix (count/category) then force.
        return ["matrix heatmap", "force graph"] + arc
    # no scalar, no categorical -> count matrix then force (then arc for reflexive).
    return ["matrix heatmap", "force graph"] + arc


def choose_selected(pattern, true_candidates, cols):
    if not true_candidates:
        return None
    if pattern in ("many_many_relationship", "reflexive_many_many_relationship"):
        # Candidates are added in ranked order (rank_relationship_charts), so the first
        # eligible one is the selector's top pick.
        return {"chart": true_candidates[0]["chart"], "mapping": true_candidates[0]["mapping"]}
    if pattern == "weak_entity":
        k2 = first(cols, lambda x: x["is_pk"] and not x["is_fk"])
        k2_ordered = k2 and (k2["dim"] in ("scalar", "temporal"))
        if k2_ordered:
            for c in true_candidates:
                if c["chart"] == "line chart":
                    return {"chart": c["chart"], "mapping": c["mapping"]}
        return {"chart": true_candidates[0]["chart"], "mapping": true_candidates[0]["mapping"]}
    return {"chart": true_candidates[0]["chart"], "mapping": true_candidates[0]["mapping"]}


def recommend(schema, table_name, selected_columns, pattern, rows=None):
    schema_n = normalize_schema(schema)
    tname_n = norm_name(table_name)
    table_def = schema_n.get("tables", {}).get(tname_n)
    if table_def is None:
        return {
            "recommended_charts": [],
            "candidates": [],
            "selected": None
        }

    cols = selected_column_meta(table_def, selected_columns)
    table_out_name = table_def.get("name", table_name)

    key_pk = all_where(cols, lambda c: c["is_pk"])
    scalar_attrs = all_where(cols, lambda c: c["dim"] == "scalar" and (not c["is_pk"]) and (not c["is_fk"]))
    temporal_attrs = all_where(cols, lambda c: c["dim"] == "temporal" and (not c["is_pk"]) and (not c["is_fk"]))
    discrete_attrs = all_where(cols, lambda c: c["dim"] == "discrete" and (not c["is_pk"]) and (not c["is_fk"]))

    candidates = []

    def add(chart, eligible, reason, mapping=None, note=None):
        item = {"chart": chart, "eligible": eligible, "reason": reason, "mapping": mapping}
        if note is not None:
            item["note"] = note
        candidates.append(item)

    if pattern in ("basic_entity", "basic_entity_inherited_key"):
        key = first(cols, lambda c: c["is_pk"])
        color = discrete_attrs[0]["name"] if discrete_attrs else None

        if key and len(scalar_attrs) >= 1:
            add("bar chart", True, "Has primary key and at least one scalar attribute.",
                {"table": table_out_name, "key": key["name"], "measure": scalar_attrs[0]["name"]})
        else:
            add("bar chart", False, "Needs primary key plus at least one scalar attribute.", None)

        if key and len(scalar_attrs) >= 2:
            m = {"table": table_out_name, "key": key["name"], "x": scalar_attrs[0]["name"], "y": scalar_attrs[1]["name"]}
            if color:
                m["color"] = color
            add("scatter diagram", True, "Has primary key and at least two scalar attributes.", m)
        else:
            add("scatter diagram", False, "Needs primary key plus at least two scalar attributes.", None)

        if key and len(scalar_attrs) >= 3:
            m = {
                "table": table_out_name,
                "key": key["name"],
                "x": scalar_attrs[0]["name"],
                "y": scalar_attrs[1]["name"],
                "size": scalar_attrs[2]["name"]
            }
            if color:
                m["color"] = color
            add("bubble chart", True, "Has primary key and at least three scalar attributes.", m)
        else:
            add("bubble chart", False, "Needs primary key plus at least three scalar attributes.", None)

        if key and len(temporal_attrs) >= 1:
            m = {"table": table_out_name, "date": temporal_attrs[0]["name"], "key": key["name"]}
            if scalar_attrs:
                m["measure"] = scalar_attrs[0]["name"]
            add("calendar chart", True, "Has primary key and at least one temporal attribute.", m)
        else:
            add("calendar chart", False, "Needs primary key plus at least one temporal attribute.", None)

        if key and len(scalar_attrs) >= 1:
            add(
                "choropleth map",
                "conditional",
                "Requires geographical key (not provable from schema); scalar measure is present.",
                {"table": table_out_name, "region": key["name"], "color": scalar_attrs[0]["name"]},
                note="Geographical property must be externally confirmed."
            )
        else:
            add("choropleth map", False, "Needs key plus scalar measure; geography remains unprovable.", None)

        if key and len(scalar_attrs) >= 1:
            add(
                "word cloud",
                "conditional",
                "Requires lexical key (not provable from schema); scalar size is present.",
                {"table": table_out_name, "text": key["name"], "size": scalar_attrs[0]["name"]},
                note="Lexical property must be externally confirmed."
            )
        else:
            add("word cloud", False, "Needs key plus scalar measure; lexicality remains unprovable.", None)

    elif pattern == "one_many_relationship":
        parent = first(cols, lambda c: c["is_fk"] and (not c["is_pk"]))
        child = first(cols, lambda c: c["is_pk"])
        scalar = first(cols, lambda c: c["dim"] == "scalar" and (not c["is_pk"]) and (not c["is_fk"]))
        dcol = first(cols, lambda c: c["dim"] == "discrete" and (not c["is_pk"]) and (not c["is_fk"]))

        if parent and child and scalar:
            m = {"table": table_out_name, "parent": parent["name"], "child": child["name"], "measure": scalar["name"]}
            add("tree map", True, "Has parent FK, child key, and scalar measure.", m)
            add("circle packing", True, "Has parent FK, child key, and scalar measure.", deepcopy(m))
        else:
            add("tree map", False, "Needs parent FK (non-PK), child PK, and scalar measure.", None)
            add("circle packing", False, "Needs parent FK (non-PK), child PK, and scalar measure.", None)

        if parent and child:
            m = {"table": table_out_name, "parent": parent["name"], "child": child["name"]}
            if dcol:
                m["color"] = dcol["name"]
            add("hierarchy tree", True, "Has parent FK and child key.", m)
        else:
            add("hierarchy tree", False, "Needs parent FK (non-PK) and child PK.", None)

    elif pattern in ("many_many_relationship", "reflexive_many_many_relationship"):
        is_reflexive = pattern == "reflexive_many_many_relationship"
        pk_fk = all_where(cols, lambda c: c["is_pk"] and c["is_fk"])
        scalar = first(cols, lambda c: c["dim"] == "scalar" and (not c["is_pk"]) and (not c["is_fk"]))
        categorical = first(cols, lambda c: c["dim"] == "discrete" and (not c["is_pk"]) and (not c["is_fk"]))
        has_scalar = scalar is not None
        has_categorical = categorical is not None

        if len(pk_fk) >= 2:
            source = pk_fk[0]["name"]
            target = pk_fk[1]["name"]
            sig = relationship_signals(rows, source, target, is_reflexive)
            weight_value = scalar["name"] if has_scalar else "count"

            def node_link_map():
                # Sankey/chord keep the legacy scalar `width` field.
                return {"table": table_out_name, "source": source, "target": target,
                        "width": scalar["name"], "pattern": pattern}

            def graph_map(with_category=False):
                # matrix/force/arc use `value` = scalar column name or the literal "count".
                m = {"table": table_out_name, "source": source, "target": target,
                     "value": weight_value, "pattern": pattern}
                if with_category and has_categorical:
                    m["category"] = categorical["name"]
                return m

            sig_str = ""
            if sig is not None:
                sig_str = " (density=%.3f, N=%d)" % (sig["density"], sig["N"])

            ranked = rank_relationship_charts(sig, has_scalar, has_categorical, is_reflexive)
            dense_or_large = (sig is not None and (sig["density"] >= DENSE or sig["N"] >= LARGE_N))

            # Node-link (Sankey/chord) is the clearest view when the relation is sparse & small;
            # when it is dense/large it is still offered (has a scalar width) but ranked below the
            # matrix, so word the reason to match which case fired.
            if dense_or_large:
                sankey_reason = ("Renderable (has a scalar width); offered as an alternative view"
                                 " — the relation is dense/large" + sig_str + ", so the matrix is ranked first.")
                chord_reason = sankey_reason
            else:
                sankey_reason = "Sparse, small relation with a scalar width" + sig_str + ": a left-to-right flow reads clearly."
                chord_reason = "Sparse, small relation with a scalar width" + sig_str + ": ribbons around a circle read clearly."

            reasons = {
                "matrix heatmap": ("Dense/large or attribute-free relation" + sig_str
                                   + ": matrix shows every pair without crossings"
                                   + ("" if has_scalar else "; cell value = edge count") + "."),
                "force graph": "Node-link topology view (clusters, hubs, bridges)"
                               + ("" if has_scalar else "; links weighted by edge count") + ".",
                "arc diagram": "Reflexive relation on one ordered axis; local vs long-range links legible.",
                "Sankey diagram": sankey_reason,
                "chord diagram": chord_reason,
            }
            for chart in ranked:
                if chart == "matrix heatmap":
                    add(chart, True, reasons[chart], graph_map(with_category=True))
                elif chart in ("force graph", "arc diagram"):
                    add(chart, True, reasons[chart], graph_map())
                else:  # Sankey / chord
                    add(chart, True, reasons[chart], node_link_map())

            # Charts the selector did not recommend for these signals -> eligible False.
            possible = ["matrix heatmap", "force graph", "Sankey diagram", "chord diagram"]
            if is_reflexive:
                possible.append("arc diagram")
            for chart in possible:
                if chart in ranked:
                    continue
                if chart in ("Sankey diagram", "chord diagram") and not has_scalar:
                    reason = "Needs a scalar relationship attribute (width); none selected."
                elif chart in ("Sankey diagram", "chord diagram"):
                    reason = "Dense/large relation" + sig_str + ": node-link becomes a hairball; matrix preferred."
                elif chart == "matrix heatmap":
                    reason = "Sparse, small relation with a scalar width" + sig_str + ": node-link preferred; matrix still renderable."
                else:
                    reason = "Not recommended for these signals" + sig_str + "."
                add(chart, False, reason, None)
            if not is_reflexive:
                add("arc diagram", False, "Arc diagram is reflexive-only; this is a many-many relationship.", None)
        else:
            for chart in ("matrix heatmap", "force graph", "Sankey diagram", "chord diagram"):
                add(chart, False, "Needs the two primary-key foreign keys of the relationship.", None)
            if is_reflexive:
                add("arc diagram", False, "Needs the two primary-key foreign keys of the relationship.", None)

    elif pattern == "weak_entity":
        k1 = first(cols, lambda c: c["is_pk"] and c["is_fk"])
        k2 = first(cols, lambda c: c["is_pk"] and (not c["is_fk"]))
        a1 = first(cols, lambda c: c["dim"] == "scalar" and (not c["is_pk"]) and (not c["is_fk"]))
        a2 = None
        if a1:
            rest = [c for c in cols if c is not a1 and c["dim"] == "scalar" and (not c["is_pk"]) and (not c["is_fk"])]
            if rest:
                a2 = rest[0]

        if k1 and k2 and a1 and (k2["dim"] in ("scalar", "temporal")):
            m = {"table": table_out_name, "series": k1["name"], "x": k2["name"], "y": a1["name"]}
            if a2:
                m["y2"] = a2["name"]
            add("line chart", True, "Needs ordered k2 (scalar/temporal) and scalar a1.", m)
        else:
            add("line chart", False, "Needs k1 (PK-FK), ordered k2 (PK non-FK), and scalar a1.", None)

        if k1 and k2 and a1:
            comp = weak_completeness(rows, k1["name"], k2["name"]) if rows is not None else None
            mapping_sb = {"table": table_out_name, "group": k1["name"], "segment": k2["name"], "value": a1["name"]}
            if comp is None:
                add(
                    "stacked bar chart",
                    "conditional",
                    "Completeness unverified (no data supplied).",
                    mapping_sb,
                    note=f"Requires near-complete k1×k2 coverage: density >= {NEAR_COMPLETE:.2f}."
                )
            elif comp["complete"]:
                add(
                    "stacked bar chart",
                    True,
                    f"Completeness satisfied: density={comp['density']:.4f} >= {NEAR_COMPLETE:.2f}.",
                    mapping_sb
                )
            else:
                add(
                    "stacked bar chart",
                    False,
                    f"Completeness failed: density={comp['density']:.4f} < {NEAR_COMPLETE:.2f}.",
                    None
                )
        else:
            add("stacked bar chart", False, "Needs k1 (PK-FK), k2 (PK non-FK), and scalar a1.", None)

        if k1 and k2 and a1:
            add(
                "grouped bar chart",
                True,
                "Needs scalar a1; not completeness-gated.",
                {"table": table_out_name, "group": k1["name"], "segment": k2["name"], "value": a1["name"]},
                note="Side-by-side comparison view."
            )
        else:
            add("grouped bar chart", False, "Needs k1, k2, and scalar a1.", None)

        if k1 and k2 and a1:
            comp = weak_completeness(rows, k1["name"], k2["name"]) if rows is not None else None
            mapping_sp = {"table": table_out_name, "ring": k1["name"], "spoke": k2["name"], "value": a1["name"]}
            if comp is None:
                add(
                    "spider chart",
                    "conditional",
                    "Completeness unverified (no data supplied).",
                    mapping_sp,
                    note=f"Requires near-complete k1×k2 coverage: density >= {NEAR_COMPLETE:.2f}."
                )
            elif comp["complete"]:
                add(
                    "spider chart",
                    True,
                    f"Completeness satisfied: density={comp['density']:.4f} >= {NEAR_COMPLETE:.2f}.",
                    mapping_sp,
                    note="Works best with small k2 cardinality."
                )
            else:
                add(
                    "spider chart",
                    False,
                    f"Completeness failed: density={comp['density']:.4f} < {NEAR_COMPLETE:.2f}.",
                    None
                )
        else:
            add("spider chart", False, "Needs k1, k2, and scalar a1.", None)

    true_candidates = [c for c in candidates if c["eligible"] is True]
    recommended = [c["chart"] for c in true_candidates]
    selected = choose_selected(pattern, true_candidates, cols)

    return {
        "recommended_charts": recommended,
        "candidates": candidates,
        "selected": selected
    }


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_rows_for_case(data_obj, selected_table):
    if data_obj is None:
        return None
    t = norm_name(selected_table)
    if isinstance(data_obj, dict):
        if "tables" in data_obj and isinstance(data_obj["tables"], dict):
            for k, rows in data_obj["tables"].items():
                if norm_name(k) == t and isinstance(rows, list):
                    return rows
            return None
        if all(isinstance(v, list) for v in data_obj.values()):
            for k, rows in data_obj.items():
                if norm_name(k) == t and isinstance(rows, list):
                    return rows
            return None
    if isinstance(data_obj, list):
        return data_obj
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--data", required=False)
    args = parser.parse_args()

    schema = load_json(args.schema)
    cases_obj = load_json(args.cases)
    data_obj = load_json(args.data) if args.data else None

    cases = as_cases_list(cases_obj)
    results = []

    for case in cases:
        case_id = case.get("case_id")
        selected_table = case.get("selected_table")
        selected_columns = case.get("selected_columns", [])
        identified_pattern = case.get("identified_pattern")

        rows = extract_rows_for_case(data_obj, selected_table) if args.data else None

        rec = recommend(
            schema=schema,
            table_name=selected_table,
            selected_columns=selected_columns,
            pattern=identified_pattern,
            rows=rows
        )

        results.append({
            "case_id": case_id,
            "selected_table": selected_table,
            "selected_columns": selected_columns,
            "identified_pattern": identified_pattern,
            "recommended_charts": rec.get("recommended_charts", []),
            "candidates": rec.get("candidates", []),
            "selected": rec.get("selected"),
        })

    out_obj = {"results": results}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
    
# import argparse
# import json
# from typing import Dict, List, Any, Tuple, Optional

# NUMERIC_TYPES = {
#     "int", "integer", "bigint", "smallint", "numeric", "decimal",
#     "float", "double", "real", "money"
# }
# TEMPORAL_TYPES = {"date", "time", "timestamp", "year"}
# TEXT_TYPES = {"varchar", "char", "text"}

# PATTERN_BASIC = {"basic_entity", "basic_entity_inherited_key"}


# def normalize_name(s: str) -> str:
#     return (s or "").strip().lower()


# def base_sql_type(sql_type: str) -> str:
#     t = normalize_name(sql_type)
#     if "(" in t:
#         t = t.split("(", 1)[0].strip()
#     return t


# def classify_dimension(sql_type: str) -> str:
#     t = base_sql_type(sql_type)
#     if t in NUMERIC_TYPES:
#         return "scalar"
#     if t in TEMPORAL_TYPES:
#         return "temporal"
#     if t in TEXT_TYPES:
#         return "discrete"
#     return "discrete"


# def parse_cases(raw: Any) -> List[Dict[str, Any]]:
#     if isinstance(raw, dict) and "cases" in raw and isinstance(raw["cases"], list):
#         return raw["cases"]
#     if isinstance(raw, list):
#         return raw
#     raise ValueError("Cases JSON must be a list or an object with key 'cases' as a list.")


# def build_table_meta(schema: Dict[str, Any], table_name: str) -> Dict[str, Any]:
#     tables = schema.get("tables", {})
#     table_lookup = {normalize_name(k): v for k, v in tables.items()}
#     tname = normalize_name(table_name)
#     if tname not in table_lookup:
#         raise ValueError(f"Table '{table_name}' not found in schema.")
#     table = table_lookup[tname]

#     columns = table.get("columns", [])
#     col_type = {}
#     original_col_name = {}
#     for c in columns:
#         cn = normalize_name(c.get("name", ""))
#         if not cn:
#             continue
#         col_type[cn] = c.get("type", "")
#         original_col_name[cn] = c.get("name", cn)

#     pk = [normalize_name(c) for c in table.get("primary_key", [])]
#     fk_entries = table.get("foreign_keys", [])
#     fk_cols = set()
#     fk_map = {}
#     for fk in fk_entries:
#         cols = [normalize_name(c) for c in fk.get("columns", [])]
#         ref_table = normalize_name(fk.get("references_table", ""))
#         for c in cols:
#             fk_cols.add(c)
#             fk_map[c] = ref_table

#     return {
#         "table_norm": tname,
#         "table_original": table_name,
#         "col_type": col_type,
#         "original_col_name": original_col_name,
#         "pk": pk,
#         "fk_cols": fk_cols,
#         "fk_map": fk_map,
#     }


# def selected_meta(meta: Dict[str, Any], selected_columns: List[str]) -> List[Dict[str, Any]]:
#     out = []
#     for c in selected_columns:
#         cn = normalize_name(c)
#         ctype = meta["col_type"].get(cn, "")
#         dim = classify_dimension(ctype) if ctype else "discrete"
#         is_pk = cn in meta["pk"]
#         is_fk = cn in meta["fk_cols"]
#         role = {
#             "name_input": c,
#             "name_norm": cn,
#             "type": ctype,
#             "dimension": dim,
#             "is_pk": is_pk,
#             "is_fk": is_fk,
#             "is_attribute": not is_pk and not is_fk,
#             "references_table": meta["fk_map"].get(cn),
#         }
#         out.append(role)
#     return out


# def first(items: List[str]) -> Optional[str]:
#     return items[0] if items else None


# def chart_candidate(chart: str, eligible: Any, reason: str, mapping: Optional[Dict[str, Any]], note: Optional[str] = None):
#     obj = {
#         "chart": chart,
#         "eligible": eligible,
#         "reason": reason,
#         "mapping": mapping,
#     }
#     if note:
#         obj["note"] = note
#     return obj


# def used_columns_count(mapping: Optional[Dict[str, Any]]) -> int:
#     if not isinstance(mapping, dict):
#         return 0
#     count = 0
#     for k, v in mapping.items():
#         if k == "table":
#             continue
#         if isinstance(v, str) and v:
#             count += 1
#     return count


# def recommend(schema: Dict[str, Any], table_name: str, selected_columns: List[str], pattern: str) -> Dict[str, Any]:
#     meta = build_table_meta(schema, table_name)
#     sel = selected_meta(meta, selected_columns)
#     pattern_n = normalize_name(pattern)

#     sel_names = [s["name_norm"] for s in sel]
#     pk_selected = [s for s in sel if s["is_pk"]]
#     fk_selected = [s for s in sel if s["is_fk"]]
#     scalar_selected = [s for s in sel if s["dimension"] == "scalar"]
#     temporal_selected = [s for s in sel if s["dimension"] == "temporal"]
#     discrete_selected = [s for s in sel if s["dimension"] == "discrete"]

#     scalar_attributes = [s for s in sel if s["dimension"] == "scalar" and s["is_attribute"]]
#     temporal_attributes = [s for s in sel if s["dimension"] == "temporal" and s["is_attribute"]]

#     candidates = []

#     if pattern_n in PATTERN_BASIC:
#         key = first([s["name_norm"] for s in sel if s["is_pk"]])

#         # bar chart
#         if key and len(scalar_attributes) >= 1:
#             m = {"table": meta["table_norm"], "key": key, "measure": scalar_attributes[0]["name_norm"]}
#             candidates.append(chart_candidate("bar chart", True, "Has key and at least one scalar attribute.", m))
#         else:
#             candidates.append(chart_candidate("bar chart", False, "Needs selected primary key and >=1 scalar attribute.", None))

#         # scatter diagram
#         if key and len(scalar_attributes) >= 2:
#             m = {"table": meta["table_norm"], "key": key, "x": scalar_attributes[0]["name_norm"], "y": scalar_attributes[1]["name_norm"]}
#             if discrete_selected:
#                 m["color"] = discrete_selected[0]["name_norm"]
#             candidates.append(chart_candidate("scatter diagram", True, "Has key and >=2 scalar attributes.", m))
#         else:
#             candidates.append(chart_candidate("scatter diagram", False, "Needs selected primary key and >=2 scalar attributes.", None))

#         # bubble chart
#         if key and len(scalar_attributes) >= 3:
#             m = {
#                 "table": meta["table_norm"],
#                 "key": key,
#                 "x": scalar_attributes[0]["name_norm"],
#                 "y": scalar_attributes[1]["name_norm"],
#                 "size": scalar_attributes[2]["name_norm"],
#             }
#             if discrete_selected:
#                 m["color"] = discrete_selected[0]["name_norm"]
#             candidates.append(chart_candidate("bubble chart", True, "Has key and >=3 scalar attributes.", m))
#         else:
#             candidates.append(chart_candidate("bubble chart", False, "Needs selected primary key and >=3 scalar attributes.", None))

#         # calendar chart
#         if key and len(temporal_attributes) >= 1:
#             m = {"table": meta["table_norm"], "date": temporal_attributes[0]["name_norm"], "key": key}
#             if scalar_attributes:
#                 m["measure"] = scalar_attributes[0]["name_norm"]
#             candidates.append(chart_candidate("calendar chart", True, "Has key and >=1 temporal attribute.", m))
#         else:
#             candidates.append(chart_candidate("calendar chart", False, "Needs selected primary key and >=1 temporal attribute.", None))

#         # choropleth map (conditional)
#         if key and len(scalar_attributes) >= 1:
#             m = {"table": meta["table_norm"], "region": key, "color": scalar_attributes[0]["name_norm"]}
#             candidates.append(chart_candidate("choropleth map", "conditional", "Structurally fits; key must be geographical.", m, note="Requires geographical key (cannot be proven from SQL type alone)."))
#         else:
#             candidates.append(chart_candidate("choropleth map", False, "Needs selected primary key and >=1 scalar attribute.", None))

#         # word cloud (conditional)
#         if key and len(scalar_attributes) >= 1:
#             m = {"table": meta["table_norm"], "text": key, "size": scalar_attributes[0]["name_norm"]}
#             candidates.append(chart_candidate("word cloud", "conditional", "Structurally fits; key must be lexical.", m, note="Requires lexical/text-key semantics (cannot be proven from SQL type alone)."))
#         else:
#             candidates.append(chart_candidate("word cloud", False, "Needs selected primary key and >=1 scalar attribute.", None))

#     elif pattern_n == "one_many_relationship":
#         parent = None
#         for s in sel:
#             if s["is_fk"] and not s["is_pk"]:
#                 parent = s["name_norm"]
#                 break
#         child = first([s["name_norm"] for s in sel if s["is_pk"]])
#         scalar_attr = first([s["name_norm"] for s in sel if s["dimension"] == "scalar" and s["is_attribute"]])

#         def hier_mapping(with_measure: bool):
#             m = {"table": meta["table_norm"], "parent": parent, "child": child}
#             if with_measure:
#                 m["measure"] = scalar_attr
#             return m

#         if parent and child and scalar_attr:
#             candidates.append(chart_candidate("tree map", True, "Has parent, child, and scalar attribute.", hier_mapping(True)))
#         else:
#             candidates.append(chart_candidate("tree map", False, "Needs parent(FK not in PK), child(PK), and scalar attribute.", None))

#         if parent and child and scalar_attr:
#             candidates.append(chart_candidate("circle packing", True, "Has parent, child, and scalar attribute.", hier_mapping(True)))
#         else:
#             candidates.append(chart_candidate("circle packing", False, "Needs parent(FK not in PK), child(PK), and scalar attribute.", None))

#         if parent and child:
#             m = {"table": meta["table_norm"], "parent": parent, "child": child}
#             disc_attr = first([s["name_norm"] for s in sel if s["dimension"] == "discrete" and s["is_attribute"]])
#             if disc_attr:
#                 m["color"] = disc_attr
#             candidates.append(chart_candidate("hierarchy tree", True, "Has parent and child.", m))
#         else:
#             candidates.append(chart_candidate("hierarchy tree", False, "Needs parent(FK not in PK) and child(PK).", None))

#     elif pattern_n == "many_many_relationship":
#         pk_fk = [s for s in sel if s["is_pk"] and s["is_fk"]]
#         source = target = None
#         if len(pk_fk) >= 2:
#             source = pk_fk[0]["name_norm"]
#             target = pk_fk[1]["name_norm"]
#         scalar_attr = first([s["name_norm"] for s in sel if s["dimension"] == "scalar" and s["is_attribute"]])

#         if source and target and scalar_attr:
#             m = {"table": meta["table_norm"], "source": source, "target": target, "width": scalar_attr}
#             candidates.append(chart_candidate("Sankey diagram", True, "Has two PK foreign keys and scalar attribute.", m))
#         else:
#             candidates.append(chart_candidate("Sankey diagram", False, "Needs two PK foreign keys and one scalar relationship attribute.", None))

#     elif pattern_n == "reflexive_many_many_relationship":
#         pk_fk = [s for s in sel if s["is_pk"] and s["is_fk"]]
#         source = target = None
#         if len(pk_fk) >= 2:
#             source = pk_fk[0]["name_norm"]
#             target = pk_fk[1]["name_norm"]
#         scalar_attr = first([s["name_norm"] for s in sel if s["dimension"] == "scalar" and s["is_attribute"]])

#         if source and target and scalar_attr:
#             m = {"table": meta["table_norm"], "source": source, "target": target, "width": scalar_attr}
#             candidates.append(chart_candidate("chord diagram", True, "Has two PK foreign keys (same parent expected) and scalar attribute.", m))
#         else:
#             candidates.append(chart_candidate("chord diagram", False, "Needs two PK foreign keys and one scalar relationship attribute.", None))

#     elif pattern_n == "weak_entity":
#         k1 = None
#         k2 = None
#         for s in sel:
#             if s["is_pk"] and s["is_fk"] and k1 is None:
#                 k1 = s["name_norm"]
#             elif s["is_pk"] and not s["is_fk"] and k2 is None:
#                 k2 = s["name_norm"]

#         scalar_attr = first([s["name_norm"] for s in sel if s["dimension"] == "scalar" and s["is_attribute"]])
#         k2_is_scalar = False
#         if k2:
#             for s in sel:
#                 if s["name_norm"] == k2:
#                     k2_is_scalar = s["dimension"] == "scalar"
#                     break

#         if k1 and k2 and k2_is_scalar and scalar_attr:
#             m = {"table": meta["table_norm"], "series": k1, "x": k2, "y": scalar_attr}
#             candidates.append(chart_candidate("line chart", True, "Has weak keys and scalar x/y requirements.", m))
#         else:
#             candidates.append(chart_candidate("line chart", False, "Needs k1(FK in PK), k2(non-FK PK) scalar, and scalar attribute.", None))

#         if k1 and k2 and scalar_attr:
#             m = {"table": meta["table_norm"], "group": k1, "segment": k2, "value": scalar_attr}
#             candidates.append(chart_candidate("stacked bar chart", True, "Has weak keys and scalar attribute.", m))
#         else:
#             candidates.append(chart_candidate("stacked bar chart", False, "Needs k1, k2, and scalar attribute.", None))

#         if k1 and k2 and scalar_attr:
#             m = {"table": meta["table_norm"], "group": k1, "segment": k2, "value": scalar_attr}
#             candidates.append(chart_candidate("grouped bar chart", True, "Has weak keys and scalar attribute.", m))
#         else:
#             candidates.append(chart_candidate("grouped bar chart", False, "Needs k1, k2, and scalar attribute.", None))

#         if k1 and k2 and scalar_attr:
#             m = {"table": meta["table_norm"], "ring": k1, "spoke": k2, "value": scalar_attr}
#             candidates.append(chart_candidate("spider chart", True, "Has weak keys and scalar attribute.", m))
#         else:
#             candidates.append(chart_candidate("spider chart", False, "Needs k1, k2, and scalar attribute.", None))

#     else:
#         candidates.append(chart_candidate("unknown", False, f"Unsupported pattern '{pattern}'.", None))

#     recommended = [c["chart"] for c in candidates if c["eligible"] is True]

#     best_candidate = None
#     best_score = (-1, -1)
#     for idx, c in enumerate(candidates):
#         if c["eligible"] is True:
#             score = (used_columns_count(c.get("mapping")), -idx)
#             if score > best_score:
#                 best_score = score
#                 best_candidate = c

#     selected = {"chart": None, "mapping": None}
#     if best_candidate is not None:
#         selected = {"chart": best_candidate["chart"], "mapping": best_candidate.get("mapping")}

#     return {
#         "recommended_charts": recommended,
#         "candidates": candidates,
#         "selected": selected,
#     }


# def main():
#     parser = argparse.ArgumentParser(description="ER-pattern chart recommender and explicit mapper.")
#     parser.add_argument("--schema", required=True, help="Path to schema summary JSON.")
#     parser.add_argument("--cases", required=True, help="Path to cases JSON.")
#     parser.add_argument("--out", required=True, help="Path to output JSON.")
#     args = parser.parse_args()

#     with open(args.schema, "r", encoding="utf-8") as f:
#         schema = json.load(f)
#     with open(args.cases, "r", encoding="utf-8") as f:
#         cases_raw = json.load(f)

#     cases = parse_cases(cases_raw)
#     results = []

#     for case in cases:
#         case_id = case.get("case_id")
#         selected_table = case.get("selected_table")
#         selected_columns = case.get("selected_columns", [])
#         identified_pattern = case.get("identified_pattern", "")

#         rec = recommend(schema, selected_table, selected_columns, identified_pattern)
#         results.append({
#             "case_id": case_id,
#             "selected_table": selected_table,
#             "selected_columns": selected_columns,
#             "identified_pattern": identified_pattern,
#             "recommended_charts": rec["recommended_charts"],
#             "candidates": rec["candidates"],
#             "selected": rec["selected"],
#         })

#     out_obj = {"results": results}
#     with open(args.out, "w", encoding="utf-8") as f:
#         json.dump(out_obj, f, indent=2, ensure_ascii=False)


# if __name__ == "__main__":
#     main()