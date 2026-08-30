"""Step 0 (data layer) — the LLM-authored deterministic SQL builder.

Compile-time artefact of the LLM-as-compiler paradigm, extended to the data-marshalling
layer: authored **once** against the clean schema dict + a selection, it emits one
parameterised PostgreSQL query that performs the join -> filter -> (aggregate) that the
offline path does in Python (``experiments/join`` -> ``experiments/filter`` ->
``experiments/aggregate``). Pushing this into the database makes aggregation and filter
statistics exact over the full table (not a 5000-row sample) and cuts transfer.

Contract (mirrors Step 1/2/3 codegen — std-lib only, schema + selection only, **never** a
pattern or gold label, so the blind/gold separation invariant holds)::

    build_selection_sql(schema, selection) -> (sql_text, params)

    selection = {
        "table":   "<base table>",
        "columns": ["<col>", ...],          # the user's selected columns
        "joins":   [ {"bring": "t.col", "as": "alias", "policy": "first"|"explode"}, ... ],
        "filters": [ {"column","op","min","max","values","value"} | group_having, ... ],
        "aggregate": { "resample":[...], "group_by":[...], "measures":[...], "having":[...] },
        "limit":   <int|None>,              # display top-N ceiling (applied last)
    }

``sql_text`` uses named ``:p0..`` placeholders; ``params`` is the matching ``{name: value}``
dict — the caller binds them (SQLAlchemy ``text()``), so filter values never touch the SQL
string (no injection surface). Identifiers are validated against the schema and quoted.

The generated query is layered exactly as the offline stages run:

  1. **j** (CTE): base table LEFT JOINed to each ``bring`` column along its FK path. A
     non-multiplying path (forward child->parent, or a 1:1 reverse) is exact; an
     ``explode`` multiplying path multiplies rows to match the offline ``explode``; a
     ``first`` multiplying path is collapsed with ``DISTINCT ON`` the base identity
     (the representative row may differ from the offline json-tiebreak — a documented,
     narrow divergence, see SUMMARY.md).
  2. **filter**: the row filters (range/in/eq/not_null/gt/ge/lt/le) as a ``WHERE`` with
     bound params, plus any ``group_having`` as ``WHERE (keys) IN (SELECT ... HAVING ...)``.
  3. **aggregate** (optional): resample buckets ``floor(col/b)*b``, ``GROUP BY`` the
     dimensions, measures (sum/avg/min/max/count/count_distinct), post-aggregate ``HAVING``.
  4. **order + limit**: measure-desc when a measure exists (top-N like Mohammed's TRUNCATE),
     else by the key columns; then ``LIMIT``.

The offline Python stages remain the authoritative implementation for the JSON fixture path
and for ``VIZER_PUSHDOWN=off`` fallback; ``compare_sql_vs_python.py`` asserts the two agree.
"""

from __future__ import annotations

import os
import sys
from typing import Any

# Reuse the single source of truth for the FK graph / shortest path, so JOIN construction
# can never drift from the offline enrich. join_tables is std-lib and gold-free.
_EXP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _EXP not in sys.path:
    sys.path.insert(0, _EXP)
from join.join_tables import find_paths  # noqa: E402


# ----------------------------------------------------------------------------- helpers
def _norm(s: Any) -> str:
    return s.lower() if isinstance(s, str) else s


def _tables(schema: dict) -> dict:
    return schema.get("tables", {}) if isinstance(schema, dict) else {}


def _find_table(schema: dict, name: str):
    for tname, tdef in _tables(schema).items():
        if _norm(tname) == _norm(name):
            return tname, tdef
    return None, None


def _resolve_col(tdef: dict, name: str) -> str | None:
    """Actual (case-correct) column name in a table, or None if absent."""
    for c in (tdef or {}).get("columns", []):
        if _norm(c.get("name")) == _norm(name):
            return c.get("name")
    return None


def _q(ident: str) -> str:
    """Quote a SQL identifier (double quotes, internal quotes doubled)."""
    return '"' + str(ident).replace('"', '""') + '"'


class _Params:
    """Allocates :p0, :p1 … named placeholders and collects their bound values."""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self._n = 0

    def add(self, value: Any) -> str:
        name = "p%d" % self._n
        self._n += 1
        self.values[name] = value
        return ":" + name


_AGG_SQL = {
    "sum": lambda col: "SUM(%s)" % col,
    "mean": lambda col: "AVG(%s)" % col,
    "avg": lambda col: "AVG(%s)" % col,
    "min": lambda col: "MIN(%s)" % col,
    "max": lambda col: "MAX(%s)" % col,
    "count": lambda col: "COUNT(*)",
    "count_distinct": lambda col: "COUNT(DISTINCT %s)" % col,
}

# Mirrors aggregate_rows._measure_alias / filter._cmp op names.
_CMP_SQL = {"gt": ">", "ge": ">=", "lt": "<", "le": "<=", "eq": "="}


def _measure_alias(m: dict) -> str:
    if m.get("as"):
        return m["as"]
    fn = (m.get("fn") or "sum").lower()
    return "count" if fn == "count" else fn + "_" + str(m.get("column"))


# ------------------------------------------------------------------- join (CTE "j")
def _build_join(schema: dict, base_name: str, base_def: dict, joins: list, params: _Params):
    """Return (select_prefix, from_sql, brought_cols, multiplies_first).

    ``select_prefix`` is the projection (``b.*`` plus each brought column aliased);
    ``from_sql`` is the ``FROM base LEFT JOIN …`` chain.
    """
    from_parts = ["%s AS b" % _q(base_name)]
    select_bits = ["b.*"]
    brought: list[str] = []
    multiplies_first = False
    existing = {_norm(c.get("name")) for c in base_def.get("columns", [])}
    alias_n = 0

    for ji, join in enumerate(joins or []):
        bring = join.get("bring") or ""
        if "." not in bring:
            continue
        target, col = bring.split(".", 1)
        paths = find_paths(schema, base_name, target)
        if not paths:
            continue
        path = paths[0]
        policy = (join.get("policy") or "first").lower()
        if any(h.get("multiplies") for h in path) and policy != "explode":
            multiplies_first = True

        prev = "b"
        for hop in path:
            alias = "j%d_%d" % (ji, alias_n)
            alias_n += 1
            on = " AND ".join(
                "%s.%s = %s.%s" % (prev, _q(fc), alias, _q(tc)) for (fc, tc) in hop["on"]
            )
            from_parts.append("LEFT JOIN %s AS %s ON %s" % (_q(hop["to"]), alias, on))
            prev = alias

        _, tdef = _find_table(schema, target)
        real_col = _resolve_col(tdef, col) or col
        as_col = join.get("as") or col
        if _norm(as_col) in existing:
            as_col = str(target) + "__" + str(col)
        existing.add(_norm(as_col))
        select_bits.append("%s.%s AS %s" % (prev, _q(real_col), _q(as_col)))
        brought.append(as_col)

    from_sql = "\n  ".join(from_parts)
    return ", ".join(select_bits), from_sql, brought, multiplies_first


# ---------------------------------------------------------------- filter (WHERE)
def _where_row_filter(f: dict, colref, params: _Params) -> str | None:
    """One row-filter predicate as SQL, or None to skip. ``colref(name)`` -> quoted ref."""
    op = (f.get("op") or "").strip().lower()
    column = f.get("column")
    if not column:
        return None
    ref = colref(column)
    if ref is None:
        return None
    if op == "not_null":
        return "%s IS NOT NULL" % ref
    if op == "range":
        bits = ["%s IS NOT NULL" % ref]
        if f.get("min") is not None:
            bits.append("%s >= %s" % (ref, params.add(f["min"])))
        if f.get("max") is not None:
            bits.append("%s <= %s" % (ref, params.add(f["max"])))
        return "(" + " AND ".join(bits) + ")"
    if op == "in":
        values = f.get("values")
        if not isinstance(values, list) or not values:
            return "FALSE"
        placeholders = ", ".join(params.add(v) for v in values)
        return "%s IN (%s)" % (ref, placeholders)
    if op == "eq":
        return "%s = %s" % (ref, params.add(f.get("value")))
    if op in _CMP_SQL and op != "eq":
        return "(%s IS NOT NULL AND %s %s %s)" % (ref, ref, _CMP_SQL[op], params.add(f.get("value")))
    return None  # unknown op -> no constraint (forward-compatible, matches offline)


def _group_having_sql(f: dict, source: str, colref, params: _Params) -> str | None:
    """Translate a group_having filter to ``(keys) IN (SELECT keys FROM source GROUP BY keys
    HAVING <cond>)`` — keeps member rows without collapsing (matches filter._apply_group_having).
    """
    group_by = f.get("group_by") or []
    having = f.get("having") or []
    if not group_by or not having:
        return None
    keys = [colref(g) for g in group_by]
    if any(k is None for k in keys):
        return None
    conds = []
    for h in having:
        expr = _AGG_SQL.get((h.get("fn") or "count").lower())
        if expr is None:
            continue
        inner = colref(h.get("column")) if h.get("column") else "*"
        op = _CMP_SQL.get((h.get("op") or "").lower())
        if op is None:
            continue
        conds.append("%s %s %s" % (expr(inner if inner else "*"), op, params.add(h.get("value"))))
    if not conds:
        return None
    keytuple = "(%s)" % ", ".join(keys)
    sub = "SELECT %s FROM %s GROUP BY %s HAVING %s" % (
        ", ".join(keys), source, ", ".join(keys), " AND ".join(conds))
    return "%s IN (%s)" % (keytuple, sub)


# ------------------------------------------------------------------------- entry
def build_selection_sql(schema: dict, selection: dict):
    """Build one parameterised PostgreSQL query for a selection. See module docstring."""
    params = _Params()
    base_name, base_def = _find_table(schema, selection.get("table"))
    if base_def is None:
        raise ValueError("unknown table: %r" % (selection.get("table"),))

    joins = selection.get("joins") or []
    filters = selection.get("filters") or []
    aggregate = selection.get("aggregate") or {}
    limit = selection.get("limit")

    # ---- CTE j: base + brought columns
    select_prefix, from_sql, brought, mult_first = _build_join(
        schema, base_name, base_def, joins, params)
    distinct = ""
    if mult_first:
        pk = [_q(c) for c in (base_def.get("primary_key") or [])]
        ident = pk or [_q(c.get("name")) for c in base_def.get("columns", [])]
        distinct = "DISTINCT ON (%s) " % ", ".join("b." + c for c in ident)
    j_cte = "j AS (\n  SELECT %s%s\n  FROM %s\n)" % (distinct, select_prefix, from_sql)

    # A column reference valid against the CTE (base columns + brought aliases).
    base_cols = {_norm(c.get("name")): c.get("name") for c in base_def.get("columns", [])}
    brought_map = {_norm(b): b for b in brought}

    def colref(name):
        real = base_cols.get(_norm(name)) or brought_map.get(_norm(name))
        return _q(real) if real else None

    # ---- WHERE (row filters + group_having), applied to j (pre-aggregate)
    where_bits = []
    for f in filters:
        if (f.get("op") or "").strip().lower() == "group_having":
            gh = _group_having_sql(f, "j", colref, params)
            if gh:
                where_bits.append(gh)
        else:
            w = _where_row_filter(f, colref, params)
            if w:
                where_bits.append(w)
    where_sql = ("\nWHERE " + " AND ".join(where_bits)) if where_bits else ""

    group_by = aggregate.get("group_by") or []
    measures = aggregate.get("measures") or []
    resamples = aggregate.get("resample") or []
    is_agg = bool(group_by or measures or resamples)

    if not is_agg:
        # ---- non-aggregate: project j, filter, order, limit
        order = ""  # order only matters for the top-N cut; keep stable by base identity
        sql = "WITH %s\nSELECT * FROM j%s%s" % (j_cte, where_sql, order)
    else:
        # ---- resample buckets as computed columns referenced by group_by
        bucket_exprs = {}
        for rs in resamples:
            col = rs.get("column")
            bucket = rs.get("bucket")
            alias = rs.get("as") or (str(col) + "_bucket")
            ref = colref(col)
            if ref is None or not bucket:
                continue
            bp = params.add(bucket)
            bucket_exprs[_norm(alias)] = (
                alias, "(FLOOR(%s::numeric / %s) * %s)::bigint" % (ref, bp, bp))

        select_bits, group_bits = [], []
        for g in group_by:
            if _norm(g) in bucket_exprs:
                alias, expr = bucket_exprs[_norm(g)]
                select_bits.append("%s AS %s" % (expr, _q(alias)))
                group_bits.append(expr)
            else:
                ref = colref(g)
                if ref is None:
                    continue
                select_bits.append(ref)
                group_bits.append(ref)

        alias_expr = {}   # measure alias -> its aggregate SQL, for HAVING + ORDER BY
        first_measure = None
        for m in measures:
            fn = (m.get("fn") or "sum").lower()
            expr_fn = _AGG_SQL.get(fn)
            if expr_fn is None:
                continue
            inner = colref(m.get("column")) if m.get("column") else "*"
            expr = expr_fn(inner if inner else "*")
            alias = _measure_alias(m)
            select_bits.append("%s AS %s" % (expr, _q(alias)))
            alias_expr[_norm(alias)] = expr
            if first_measure is None:
                first_measure = expr

        # ---- HAVING (post-aggregate), referencing measure exprs / group cols
        having_bits = []
        for h in aggregate.get("having") or []:
            col = h.get("column")
            expr = alias_expr.get(_norm(col))
            if expr is None:
                gref = colref(col)
                expr = gref
            if expr is None:
                continue
            op = (h.get("op") or "").lower()
            if op == "range":
                if h.get("min") is not None:
                    having_bits.append("%s >= %s" % (expr, params.add(h["min"])))
                if h.get("max") is not None:
                    having_bits.append("%s <= %s" % (expr, params.add(h["max"])))
            elif op in _CMP_SQL:
                having_bits.append("%s %s %s" % (expr, _CMP_SQL[op], params.add(h.get("value"))))
        having_sql = ("\nHAVING " + " AND ".join(having_bits)) if having_bits else ""

        group_sql = ("\nGROUP BY " + ", ".join(group_bits)) if group_bits else ""
        # Top-N: measure-desc when present (most useful cut), else by the key columns.
        order_sql = ""
        if first_measure is not None:
            order_sql = "\nORDER BY %s DESC NULLS LAST" % first_measure
        elif group_bits:
            order_sql = "\nORDER BY " + ", ".join(group_bits)
        sql = "WITH %s\nSELECT %s\nFROM j%s%s%s%s" % (
            j_cte, ", ".join(select_bits), where_sql, group_sql, having_sql, order_sql)

    if limit is not None:
        sql += "\nLIMIT %s" % params.add(int(limit))
    return sql, params.values


# ------------------------------------------------------------------------- CLI
def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--selection", required=True, help="selection JSON")
    args = ap.parse_args()
    with open(args.schema, encoding="utf-8") as f:
        schema = json.load(f)
    with open(args.selection, encoding="utf-8") as f:
        selection = json.load(f)
    sql, prm = build_selection_sql(schema, selection)
    print(sql)
    print("\n-- params:", json.dumps(prm, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
