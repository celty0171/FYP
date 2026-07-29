# VizER (Hannan, MEng 2024) — full-pipeline summary

Summary of `mohammed_hannan_meng_final_report_2024.pdf` (Imperial MEng, supervisor
Peter McBrien), focused on **how the full pipeline was built**. This is the original VizER
that the present FYP re-interprets with LLMs; see §6 for the relationship.

## One-line summary

A **full-stack web app** (React front end + Java/Spring Boot back end + JDBC to PostgreSQL)
that recommends visualisations **from the database's conceptual model (ER model / schema
patterns), not from the data values**. Pipeline = *connect & read metadata → two-round
pattern matching to identify the ER pattern and recommend charts → build a pattern-specific
SQL query for the result data → render interactive charts on the front end*.

## 1. Theoretical basis: two mapping systems

**(1) Five visualisation schema patterns** — decided purely from PK/FK structure (ER shape,
not data values):

| Pattern | Rule (column analysis) |
|---|---|
| Basic Entity | none of the chosen columns is a foreign key |
| Basic Entity (inherited key) | the **whole** PK is inherited as an FK from a single parent |
| Weak Entity | **part** of the PK is an FK to a single parent |
| One-Many | one FK present that is **not** part of the PK |
| Many-Many | PK composed of **two FKs to different tables** |
| Reflexive Many-Many | the two PK/FKs point to the **same** table (e.g. borders country1/country2) |

**(2) SQL data-type grouping** — decides *which* chart within a pattern's group:
- PostgreSQL types grouped into **lexical / numeric / temporal / geographical**.
- McBrien's **scalar** (continuous, ordered — numeric/date) vs **discrete** (categorical) dimensions.
- geographical type inferred even from **column/table name** (e.g. `country`, `city` → geographical, used for choropleth).

## 2. Core algorithm: two-round pattern matching (the heart of the pipeline)

After the user ticks some columns, back end `dfRecommendVisualisations` runs:

**Round 1 — identify the ER pattern.** Analyse only the **PK/FK structure** of the chosen
columns via `isBasicEntity` / `isWeakEntity` / `isManyManyRelationship` etc.

**Round 2 — recommend concrete charts.** Knowing the pattern gives the candidate chart group;
then analyse the **data types + number of attributes** of all chosen columns to test each chart.
The test functions are tiny, e.g.:

```java
private boolean bar(List<String> attTypes) {
    return attTypes.size()==1 && isScalarType(attTypes.get(0));           // one scalar attribute
}
private boolean scatter(List<String> attTypes) {
    return attTypes.size()==2 && attTypes.stream().allMatch(this::isScalarType); // two scalars
}
```

**Pattern → chart-group mapping** (one of his contributions):
- **Basic** → bar / calendar / scatter / bubble / choropleth / word cloud
- **Weak** → line / stacked bar / grouped bar / spider (some need the *completeness* property)
- **One-Many** → treemap / hierarchy tree / circle packing (hierarchical)
- **Many-Many** → sankey / chord / force network
  - **reflexive → chord** (shows within-entity interaction)
  - **non-reflexive → sankey or network**

Each chart also carries a subjective **key-cardinality cap** (e.g. bar ≤ 100), because amCharts
lags / mis-renders on too much data.

## 3. The two modes (user journeys)

**DATA-FIRST (main) — "pick data, then get charts":**
1. **Connect**: username/password/host/port/database → JDBC + Postgres driver open a connection.
2. **Read metadata**: `DatabaseMetaData.getTables` over the public schema; extract each table's
   column names, column types, PKs, FKs into a list of `TableMetadata` objects shown to the user
   (columns tagged with type + PK/FK).
3. **Select columns + filters**: checkboxes; filters (`=`,`!=`,`<`,`LIKE`,… → `WHERE`) and a row
   limit (→ `LIMIT n`).
4. **Two-round matching** (§2) → identify pattern + build the chart candidate list.
5. **Pattern-specific SQL**: each pattern uses a different query template (weak entity → `GROUP BY`
   parent key + `SUM`; compound FKs concatenated with `||` into one column; `NULL`s filtered out —
   McBrien's "mandatory attribute" transformation).
6. **Render**: result data + pattern + options returned; **each chart is its own React component**,
   click to render, with order/truncate controls (to honour cardinality caps and reduce clutter).

**VIZ-FIRST (extension) — "pick a chart, then find data that fits"** (reversed order):
1. Connect (as above).
2. Pick a chart type → back end finds **which tables** can be that chart's pattern.
3. Pick a table → `vfGenerateOptions` enumerates **all column combinations** of that table that can
   draw the chart (e.g. economy as scatter: every ordered pair of scalar attributes → 30 options).
4. Pick a specific column combination + optional axis/filters.
5. Generate (request carries the `pattern` field so the back end need not re-identify it).

## 4. Tech stack & architecture

| Layer | Choice | Reason |
|---|---|---|
| Front end | **React JS** + **Ant Design** | virtual DOM; component reuse across both modes |
| Back end | **Java + Spring Boot** (REST) | JDBC's ability to read DB **metadata** is the key advantage |
| Data | **JDBC API** → **PostgreSQL** | connect, run SQL, read metadata (PK/FK/types) |
| Charts | **amCharts** (main) + **Google Charts** (calendar only) | amCharts range/docs; Google Charts only because amCharts lacks a calendar chart |

REST endpoints: `/api/v1/db-login`, `/tables`, `/df-visualise` (main); `/vf-select`,
`/vf-generate`, `/vf-execute` (extension).

## 5. Key development trade-offs (relevant to the FYP)

1. **Dropped whole-database reverse translation.** The initial plan reverse-translated the *entire*
   DB into an ER model on connect (tried the Amazing-ER library) but it was slow and failed on weak
   entities. Switched to **column analysis on only the user's selected columns** — faster and more
   scalable. His most important architectural decision.
2. **Per-chart React components** made adding the calendar chart (a second library) painless.
3. **Evaluation** on the **Mondial / Bank Branch / Family History** databases: per-pattern test
   cases for correct identification (Table 5.1 all PASS) and recommendation. Known defect: selecting
   only a weak entity's **child key** is misread as a basic entity (no FK present) → fix by analysing
   the table's **whole** PK, not just the selected columns.

## 6. Relationship to the present FYP

- Hannan is a **deterministic rule engine**: `classify` uses hard-coded PK/FK rule functions
  (`isBasicEntity` …); `recommend` uses hard-coded type-condition functions (`bar()`, `scatter()`).
- This FYP replaces that **same pattern classification + chart recommendation** with an **LLM**
  (either per-case prompting, or having the LLM author a deterministic program once). The repo's
  `classify_vizer_pattern.py`, the pattern taxonomy, and the DATA-FIRST task generation reproduce
  his rules as the comparison baseline.
- He used amCharts/Google Charts; this FYP moves to **self-generated D3 v7 renderers** — so the
  current work on sankey/chord/arc/force overlap reduction directly tackles the "complex relationship
  charts render cluttered / crash on too much data" pain point he noted but did not solve.

## 7. His implementation vs this FYP's implementation (as built)

Based on the current repository (Step 1 = `results/prompt_v9_codegen/gpt_generated.py`,
Step 2 = `results/step2_codegen/gpt_recommend_charts.py`, Step 3 = the `results/viz_codegen_*`
renderer suite, chained by `web_pipeline/server.py`). The organising difference: Hannan hand-wrote
one Java rule engine; this FYP has an **LLM author deterministic standard-library Python programs**
that are then run reproducibly ("LLM-as-compiler"), and compares them against a hand-written rule
baseline (`scripts/classify_vizer_pattern.py`).

| Aspect | Hannan 2024 (VizER) | This FYP (as built) |
|---|---|---|
| **Paradigm** | Hand-written deterministic rule engine | **LLM authors** the deterministic programs once; then run reproducibly. Rule baseline kept for comparison |
| **Schema source** | Live PostgreSQL via **JDBC metadata** (PK/FK/types) at run time | Offline: `mondial_schema.sql` → `extract_mondial_schema.py` → **clean** JSON summary (`mondial_schema_summary_clean.json`, no pattern labels) fed to the model |
| **Blind/gold split** | N/A (rules see everything) | Deliberate: blind cases drive prediction; gold patterns read **only** at evaluation — no label leakage |
| **Patterns** | 5 patterns (basic incl. inherited key as a sub-case) | **6** explicit: adds `basic_entity_inherited_key` as its own label (`gpt_generated.py` lines 7–12) |
| **Step 1 — classify** | Java `isBasicEntity`/`isWeakEntity`/`isManyManyRelationship` over selected columns | `classify_selection()` — same PK/FK logic in Python, **stricter on partial-PK selections**, emits `predicted_pattern` + `reason`; 9/9 on blind cases |
| **Step 2 — recommend** | Java per-chart boolean tests (`bar()`, `scatter()`) on data types + attribute count | `recommend()` — same type/attribute tests, **plus a data-driven relationship selector** |
| **Many-many chart choice** | Fixed rule: reflexive → chord, else sankey/network | **Measures the data**: `density`, `N`, `symmetric` from rows → ranked chart list. Node-link (sankey/chord) only while *sparse & small & has scalar*; once **dense or large** the **matrix heatmap** leads (avoids hairball). Thresholds `DENSE=0.10`, `LARGE_N=200` |
| **Relationship chart set** | sankey, chord, force network | sankey, chord, force, **+ matrix heatmap** and **arc diagram** (arc reflexive-only); `value` = scalar column *or* literal `"count"` so attribute-free relations are covered |
| **Cardinality limits** | Subjective per-chart caps (e.g. bar ≤ 100); user "truncate" button | Handled by the density/size selector + optional **prepare stages** (filter/aggregate) rather than fixed caps |
| **Step 3 — render** | amCharts (+ Google Charts for calendar); each chart a React component | **LLM-authored D3 v7 renderers**, one `render(mapping, rows)` per chart, std-lib Python emitting standalone HTML; **18 charts across all 5 patterns** |
| **Overlap reduction** | Noted as a problem (clutter/crash on big data); mitigated only by truncation | **Explicit algorithms**: arc/chord spectral (Fiedler) ordering → min arc/chord span; sankey iterated two-layer barycentre; force group-separation + collision. Measured crossing cuts of ~70–94 % |
| **Modes** | DATA-FIRST + VIZ-FIRST (interactive) | DATA-FIRST focus; batch task generation + scored evaluation the primary workflow |
| **Prepare / SQL** | Pattern-specific SQL built via JDBC (`GROUP BY`/`SUM`, `WHERE`, `LIMIT`) | Std-lib **prepare stages** — `filter/apply_filters.py`, `aggregate/aggregate_rows.py`, `join/join_tables.py` — operate on JSON rows offline (no live DB) |
| **Front end** | React + Ant Design SPA | Std-lib `ThreadingHTTPServer` (`web_pipeline/server.py` + `index.html`), **no model calls at serve time** — chains the three authored programs, renders in a sandboxed iframe |
| **Charting stack** | amCharts / Google Charts (high-level, version-drift risk) | Pinned **D3 v7** only, no brace-templating, structural + static-JS validation — dissolves the library-version-drift failure mode |
| **Evaluation** | Manual per-pattern PASS/FAIL tables over 3 databases | Automated: `evaluate_llm_run.py` scores a run dir (`evaluation.json`/`summary.md`); deterministic rule baseline via `classify_vizer_pattern.py` + `evaluate_vizer_baseline.py` |
| **LLM role** | None | Central: self-hosted Qwen on HPC (Qwen3-14B for Step 1/2, Coder-32B for Step 3) or manual web chat (GPT/Claude) as fallback |

**Net difference.** Hannan proves the *concept* (schema patterns → chart recommendation) works as a
deterministic app. This FYP asks the *research* question — can an LLM reproduce that rule engine (and
the D3 renderers) as authored programs — and, in doing so, adds a data-driven relationship-chart
selector, two extra relationship charts (matrix, arc), and principled overlap-reduction algorithms
that his amCharts-based renderers never had.
