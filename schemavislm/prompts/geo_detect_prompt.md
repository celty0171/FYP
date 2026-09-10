# Geographical-column detection prompt (opt-in LLM refinement)

This is the contract for the optional LLM layer in `schemavislm/geodetect/`
(`_llm_geo_columns`), enabled with `SCHEMAVISLM_LLM_GEO=on` and a `DASHSCOPE_API_KEY`. It **refines**
the deterministic heuristics — it never replaces them: the final geographical set is
`heuristics ∪ llm`, and any error/missing key falls back to heuristics alone.

## Purpose

Decide which columns of a connected database are **geographical region identifiers** — a value
that names a place drawable on a map (country, province/state, city, continent). Whether a
column is geographical cannot be proven from its SQL type, and a user's own DB may name the
concept `region`, `nation`, `territory`, … so the closed Mondial list does not generalise.

## Input

A compact schema digest: every table with its columns (SQL type, `pk`/`fk` flags) and, for text
columns, a few sample values to disambiguate names.

## Output (strict)

A single JSON object, no prose:

```json
{ "geographical": ["country.code", "city.name", "encompasses.continent"] }
```

- List every geographical column as `"table.column"`; empty list if none.
- Use **only** the `table.column` names given — never invent names (invalid pairs are dropped).
- A column is geographical when its values identify a mappable place (by name or standard code,
  e.g. country names or ISO alpha-2/alpha-3/numeric codes) — **including** when it holds such
  codes under a generic name like `code`/`id`/`cc`, inferred from the sample values (`US`, `USA`,
  `DE`). This LLM layer is the **safety net** for exactly these cases the name-based heuristics
  miss, so inspect the sample values, not just the column name.
- A column is **not** geographical when it is a plain measure, a date, a person/organisation
  name, or an opaque surrogate id with no geographic meaning.

## Invariants preserved

- The model returns **only** the geographical flag — never a chart type, ER pattern, mapping, or
  any recommendation — so the blind/gold separation and the Step-2→Step-3 field-name contract are
  untouched.
- A geographical badge only makes the choropleth *offerable*; it is still gated at render time by
  whether the region values actually resolve to the world basemap (see
  `render_choropleth_reference.py::region_match_rate`), so a false positive cannot produce a
  blank map.
