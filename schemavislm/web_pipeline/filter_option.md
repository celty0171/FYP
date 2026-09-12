# Filter / Aggregate / Join — Usage guide

> On top of the original "pick a table + pick columns", the web app adds three optional
> data-preparation stages: **Join** (bring in a column from another table), **Filter** (subset rows of
> the same table), and **Aggregate** (summarise rows of the same table). All are optional; leaving them
> empty reproduces the original behaviour. The fixed pipeline order is
> **Join → Filter → Aggregate → Step 1/2/3**.

---

## At a glance

| Stage | What it does | When to use |
|---|---|---|
| **Join** | Attach a column from a **related table** to each row via the foreign-key graph | The column you want isn't in the base table (e.g. `country_population` by `continent`) |
| **Filter** | Keep only the rows that **match a condition** (WHERE) | Restrict to a time range or category (e.g. `year 1990–2020`, `continent = Europe`) |
| **Aggregate** | Collapse many rows into **one row per group** (group-by + measures) | You want sums / averages / counts, not raw rows (e.g. total population per continent) |

- **Pattern-safe**: Join only adds an attribute column — it never changes the ER pattern Step 1
  identifies. Aggregate produces a *derived table*, usually classified as `basic_entity`.
- **Recommendations adapt**: because the data changes, Step 2 re-recommends charts on the new data.

---

## Basic flow

1. **Pick a table + tick columns** (top-left "1. Selection"). Required; the other three are optional.
2. Configure Join / Filter / Aggregate (see below).
3. Click **"Run pipeline"**. The right side shows the pattern and recommended-chart **pills**; click a
   pill to render that chart.
4. After changing any stage, **click Run again**.

---

## Join — "Related columns (join)"

**Purpose.** When the column you want lives in another table, pull it in along the foreign-key path;
afterwards it can be filtered and grouped just like a native column.

**Steps.**
1. The "Related columns (join)" dropdown lists the **reachable foreign columns** from the current
   table, tagged `N-hop`; a `⚠ may duplicate` marks a join that can multiply rows.
2. Pick one (e.g. `encompasses.continent`) and click **"+ add related column"**; it becomes a chip.
3. If the column is marked `⚠` (many-to-many, e.g. a country spanning two continents), the chip shows a
   `first / explode` toggle:
   - **`first`** (default) keeps one match per row, so the **row count is unchanged** (safe default).
   - **`explode`** expands one row per match, so the **row count grows** — good for filtering to one
     category.
4. Once joined, the new column **automatically appears** in the Filters and Aggregate options.

> On a name clash the column is namespaced, e.g. bringing `province.population` into a table that
> already has `population` → `province__population`.

---

## Filter — "2. Filters"

**Purpose.** Keep only the matching rows; it never changes what a row *means*.

**Steps.** The panel **auto-builds a control per column** from its type:
- **Numeric / temporal** (e.g. `year`, `population`) → two "min – max" boxes (the placeholder shows the
  real data range); fill either or both; empty = unbounded.
- **Categorical** (e.g. `continent`) → a checklist, all ticked by default (= no filter); untick some to
  keep only the ticked values.
- **High-cardinality** columns (too many distinct values) show a hint instead of a control.

A one-line **summary** below shows the active conditions; "Clear filters" resets them.

---

## Aggregate — "3. Aggregate"

**Purpose.** Collapse rows into "one row per group". The result is a derived table (group keys = primary
key, measures = attributes), usually classified as `basic_entity` and visualised through the
**existing** Step 1→2→3 pipeline.

**Steps.**
- **Group by**: tick the grouping key(s) (e.g. `continent` or `year`).
- **Measures**: each row is "function + column + alias"; functions are
  `sum / mean / min / max / count / count_distinct`; "+ measure" adds more. (`count` needs no column.)
- **Resample (optional)**: bucket a numeric / temporal column, e.g. `year` bucket `10` as `decade`; the
  derived `decade` is added to the Group-by options.

> With aggregation on, the chart describes **groups**, not raw rows (the panel notes
> "chart describes groups, not raw rows").

---

## A worked example

**Goal.** See population change over time in a continent (e.g. Europe).

**View A — per-country trends (line chart).**
1. Table `country_population`; tick `country`, `year`, `population`.
2. **Join**: add `encompasses.continent` (policy `first`).
3. **Filter**: in Filters, tick only `Europe`.
4. **Aggregate**: leave empty.
5. **Run** → `weak_entity` → **line chart** (one line per country over years).

**View B — continent total over time.**
- Same first three steps; then **Aggregate**: Group by `year`, Measure `sum(population)`.
- **Run** → `basic_entity` → a bar chart of yearly totals.

**Rule of thumb.** Decide **where the data comes from** (table + Join), then **which part to see**
(Filter), then **how to summarise** (Aggregate), then Run and pick a chart. Any stage left empty = no-op.

---

## Troubleshooting

- **No change after editing** → click **Run** again; if `server.py` was edited, **restart the server**
  (it loads the code at startup).
- **Blank chart** → usually D3 failed to load. The server now **inlines** D3 into each chart's HTML
  (works offline); if it is still blank, hard-refresh (**Ctrl-Shift-R**) and check **F12 → Console** for
  errors.
- **"no rows match the current filter"** → the filter is too strict; relax it.
