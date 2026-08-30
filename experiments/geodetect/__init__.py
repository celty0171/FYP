"""Database-agnostic detection of *geographical* columns — generic to any database.

Background
----------
A choropleth map needs the entity's key to be a **geographical region identifier** (a country,
province, city …). Whether a column is geographical cannot be proven from its SQL type alone, so
the original pipeline hard-coded Mondial's specific table/column names (``country``, ``city`` …).
That does not generalise: a user's own database may name the same concept ``region``, ``nation`` or
``territory``. This module replaces the closed Mondial lists with two layers that work on any DB:

1. **Generic heuristics (always run).** A *text* column is geographical when its name — or the name
   of the table it foreign-keys into — matches a generic geo vocabulary (:data:`GEO_TOKENS`), or it
   is the key / conventional label of a table whose own name is geographic. The vocabulary is
   generic but a superset of Mondial's names, so Mondial detection is unchanged.
2. **Optional LLM refinement (opt-in, cached).** When enabled and a client is supplied,
   :func:`detect_geo_columns` additionally asks an LLM which columns are geographical region
   identifiers and unions the answer in. Any error / missing key falls back to layer 1, so the
   pipeline never breaks when the LLM is unavailable.

The result is a set of ``(table, column)`` pairs. The server computes it once per connected schema
(caching by a schema fingerprint) and injects it onto the schema dict under ``"_geo_columns"`` so
downstream consumers (the LLM chart selector) see the same, refined decision without re-running the
LLM. :func:`semantic_types` then turns a column's SQL dimension + geo flag into the paper's UI
badges (numeric / temporal / lexical / geographical).

Std-lib only (the optional LLM client is injected by the caller).
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# --- SQL type -> dimension (shared with the server / selector) -------------------------------
NUMERIC_TYPES = {"INT", "INTEGER", "BIGINT", "SMALLINT", "NUMERIC", "DECIMAL",
                 "FLOAT", "DOUBLE", "REAL", "MONEY"}
TEMPORAL_TYPES = {"DATE", "TIME", "TIMESTAMP", "YEAR"}
TEXT_TYPES = {"VARCHAR", "CHAR", "TEXT"}


def base_sql_type(type_str: Any) -> str:
    return str(type_str or "").strip().upper().split("(")[0].strip()


def dim_of(type_str: Any) -> str:
    """Coarse dimension of a SQL type: scalar / temporal / discrete / other."""
    b = base_sql_type(type_str)
    if b in NUMERIC_TYPES:
        return "scalar"
    if b in TEMPORAL_TYPES:
        return "temporal"
    if b in TEXT_TYPES:
        return "discrete"
    return "other"


# --- Generic geographic vocabulary -----------------------------------------------------------
# A generic set of place-entity tokens. Matched against a (de-digited, tokenised) table or column
# name. It is a *superset* of Mondial's hard-coded names (country/city/province/continent/…), so
# Mondial keeps behaving identically, while a user's ``nation`` / ``region`` / ``territory`` table
# is now recognised too. False positives here are self-correcting: choropleth is still gated at
# render time by whether the region values actually resolve to the world basemap.
GEO_TOKENS = {
    # Mondial's own entity/column names (parity)
    "country", "city", "province", "continent", "sea", "river", "lake", "island",
    "mountain", "desert", "organization", "capital", "region",
    # common synonyms for the same concepts
    "nation", "state", "town", "village", "municipality", "county", "district",
    "territory", "borough", "canton", "prefecture", "department", "commune",
    "ocean", "place", "location", "geo", "address",
    # standard region-code column names: a column literally holding an ISO country code is a
    # geographical identifier even when its table isn't obviously geographic. After `_tokens`
    # folds trailing digits + splits, these cover iso / iso2 / iso3 / iso_a2 / iso_a3 / iso3166 /
    # alpha2 / alpha3 / alpha_3 / cca2 / cca3 / ccn3, etc.
    "iso", "alpha", "cca", "ccn",
}

# Conventional human-readable label columns of an entity table.
LABEL_NAME_HINTS = {"name", "title", "label"}


def _tokens(name: Any) -> list[str]:
    """Lower-case, drop a trailing numeric suffix (``country1`` -> ``country``), split on
    non-alphanumerics."""
    n = re.sub(r"[0-9]+$", "", str(name or "").strip().lower())
    return [p for p in re.split(r"[^a-z0-9]+", n) if p]


def _name_is_geo(name: Any) -> bool:
    parts = _tokens(name)
    joined = "".join(parts)
    return joined in GEO_TOKENS or any(p in GEO_TOKENS for p in parts)


def _table_is_geo(table: Any) -> bool:
    return _name_is_geo(table)


def geo_columns(schema: dict[str, Any]) -> set[tuple[str, str]]:
    """Layer-1 heuristic set of geographical ``(table, column)`` pairs for the whole schema.

    Only *text-valued* columns (dimension not scalar/temporal) can be geographical identifiers.
    A column qualifies when its own name is geographic, it foreign-keys into a geographic table,
    or its table is geographic and the column is that table's key / a conventional label."""
    out: set[tuple[str, str]] = set()
    for table, tdef in (schema.get("tables") or {}).items():
        pk = set(tdef.get("primary_key") or [])
        fk_ref: dict[str, str] = {}
        for fk in tdef.get("foreign_keys") or []:
            for c in fk.get("columns") or []:
                if fk.get("references_table"):
                    fk_ref.setdefault(c, fk["references_table"])
        own_geo = _table_is_geo(table)
        for col in tdef.get("columns") or []:
            name = col.get("name") if isinstance(col, dict) else col
            typ = col.get("type", "") if isinstance(col, dict) else ""
            if dim_of(typ) in ("scalar", "temporal"):
                continue                       # numeric / temporal are never geographical
            ref = fk_ref.get(name)
            is_geo = (
                _name_is_geo(name)
                or (ref is not None and _table_is_geo(ref))
                or (own_geo and (name in pk or str(name).lower() in LABEL_NAME_HINTS))
            )
            if is_geo:
                out.add((table, name))
    return out


def semantic_types(dim: str, is_geo: bool) -> list[str]:
    """The paper's semantic data type(s) for a column, from its dimension + geo flag:
    numeric / temporal / lexical / geographical. A text place name is both lexical (word cloud)
    and geographical (choropleth); numeric and temporal are exclusive."""
    if dim == "scalar":
        return ["numeric"]
    if dim == "temporal":
        return ["temporal"]
    return ["lexical", "geographical"] if is_geo else ["lexical"]


# --- Schema fingerprint + LLM refinement -----------------------------------------------------
def schema_fingerprint(schema: dict[str, Any]) -> str:
    """Stable identity of a schema's table/column shape, for caching the detection result."""
    parts: list[str] = []
    for table in sorted(schema.get("tables") or {}):
        tdef = schema["tables"][table]
        names = [c.get("name") if isinstance(c, dict) else c for c in tdef.get("columns") or []]
        parts.append(table + ":" + ",".join(str(n) for n in names))
    return "|".join(parts)


_CACHE: dict[tuple[str, bool], set[tuple[str, str]]] = {}


def _all_columns(schema: dict[str, Any]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for table, tdef in (schema.get("tables") or {}).items():
        for col in tdef.get("columns") or []:
            name = col.get("name") if isinstance(col, dict) else col
            out.add((table, name))
    return out


def _schema_digest(schema: dict[str, Any], tables_view: Any = None,
                   sample: int = 4) -> str:
    """A compact, LLM-friendly description of the schema: each table's columns with SQL type,
    key/fk flags and — for text columns — a few sample values (helps disambiguate names)."""
    lines: list[str] = []
    for table in sorted(schema.get("tables") or {}):
        tdef = schema["tables"][table]
        pk = set(tdef.get("primary_key") or [])
        fk_cols: set[str] = set()
        for fk in tdef.get("foreign_keys") or []:
            for c in fk.get("columns") or []:
                fk_cols.add(c)
        rows = []
        if tables_view is not None:
            try:
                rows = tables_view.get(table) or []
            except Exception:
                rows = []
        lines.append("TABLE " + table)
        for col in tdef.get("columns") or []:
            name = col.get("name") if isinstance(col, dict) else col
            typ = col.get("type", "") if isinstance(col, dict) else ""
            tags = []
            if name in pk:
                tags.append("pk")
            if name in fk_cols:
                tags.append("fk")
            note = " [" + ",".join(tags) + "]" if tags else ""
            samp = ""
            if dim_of(typ) not in ("scalar", "temporal") and rows:
                seen: list[str] = []
                for r in rows:
                    v = r.get(name) if isinstance(r, dict) else None
                    if v not in (None, "") and str(v) not in seen:
                        seen.append(str(v))
                    if len(seen) >= sample:
                        break
                if seen:
                    samp = "  e.g. " + ", ".join(seen)
            lines.append("  " + str(name) + " : " + str(typ) + note + samp)
    return "\n".join(lines)


_SYSTEM = (
    "You label which database columns are GEOGRAPHICAL region identifiers — a value that names a "
    "place that can be drawn on a map (country, province/state, city, continent, etc.). Output "
    "ONLY a JSON object, no prose.\n\n"
    "A column is geographical when its values identify a mappable place (by name or standard code, "
    "e.g. country names or ISO alpha-2/alpha-3/numeric codes) — INCLUDING when it holds such codes "
    "under a generic name like 'code', 'id', 'cc' (infer this from the sample values, e.g. 'US', "
    "'USA', 'DE'). A column is NOT geographical when it is a plain measure, a date, a "
    "person/organisation name, or an opaque surrogate id with no geographic meaning.\n\n"
    "Rules:\n"
    "- Judge from the column name, its table, and the sample values shown — this is the safety net "
    "for geographical columns the deterministic heuristics miss (e.g. an ISO-code column named "
    "generically), so inspect the sample values, not just the name.\n"
    "- Use ONLY the table.column names given; never invent names.\n"
    "- Do NOT output chart types, ER patterns, or any recommendation — only the geographical flag.\n\n"
    'Output shape: {"geographical": ["table.column", ...]}  (list every geographical column; '
    "empty list if none)."
)


def _llm_geo_columns(schema: dict[str, Any], tables_view: Any, client: Any) -> set[tuple[str, str]]:
    """Ask the LLM which columns are geographical; return the validated ``(table, col)`` set.
    Any failure (no client, bad answer, network) yields the empty set so the caller keeps the
    heuristic result."""
    if client is None:
        return set()
    try:
        user = "Schema:\n" + _schema_digest(schema, tables_view) + \
            '\n\nReturn {"geographical": [...]} listing every geographical column as "table.column".'
        ans = client.chat_json(_SYSTEM, user)
    except Exception:
        return set()
    valid = _all_columns(schema)
    out: set[tuple[str, str]] = set()
    for item in (ans.get("geographical") if isinstance(ans, dict) else None) or []:
        if not isinstance(item, str) or "." not in item:
            continue
        table, _, col = item.partition(".")
        pair = (table.strip(), col.strip())
        if pair in valid:
            out.add(pair)
    return out


def detect_geo_columns(schema: dict[str, Any], tables_view: Any = None,
                       client: Any = None, use_llm: bool = False) -> set[tuple[str, str]]:
    """Resolve the geographical columns of ``schema``: always the layer-1 heuristics, unioned with
    the optional LLM refinement when ``use_llm`` and a ``client`` are given. Cached per schema
    fingerprint so the (possibly LLM) detection runs once per connected database."""
    key = (schema_fingerprint(schema), bool(use_llm and client is not None))
    cached = _CACHE.get(key)
    if cached is not None:
        return set(cached)
    result = geo_columns(schema)
    if use_llm and client is not None:
        result = result | _llm_geo_columns(schema, tables_view, client)
    _CACHE[key] = set(result)
    return set(result)


def resolved_geo_columns(schema: dict[str, Any]) -> set[tuple[str, str]]:
    """The geographical columns to use for ``schema``: the server-injected, possibly LLM-refined
    set (``schema["_geo_columns"]``) when present, else the pure heuristic set. Lets any consumer
    that only has the schema (e.g. the LLM chart selector) reuse the refined decision without
    re-running detection."""
    inj = schema.get("_geo_columns")
    if inj is not None:
        return {(p[0], p[1]) for p in inj if isinstance(p, (list, tuple)) and len(p) == 2}
    return geo_columns(schema)


def inject(schema: dict[str, Any], geo: Iterable[tuple[str, str]]) -> None:
    """Record the resolved geo set on the schema dict so downstream consumers can read it."""
    schema["_geo_columns"] = sorted([list(p) for p in geo])
