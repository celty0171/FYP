# NL → visualisation test set (David Bull functional tasks)

An **external, unseen** test set for the natural-language → visualisation pipeline, adapted from
the 13 functional-test tasks set by Imperial staff for David Bull's MSc project (report Table 5.1).
Because these tasks were written by third parties (not derived from our schema), they probe
**generalisation** rather than in-distribution behaviour — the gap David's report itself leaves open.

David solved these with a deterministic tool over **custom SQL**; here the same wording is typed
into our **web NL box** and we measure how far the LLM NL parser + Step-1/2/3 pipeline gets on its
own. Gold answers are in `gold.json` (Mondial column names verified against
`mondial_database/mondial_schema_summary_clean.json`).

## How to run (web front end)

1. Start the server against the live Mondial Postgres (see repo `run_local.sh`).
2. For each task, paste the **NL input** into the request/purpose box and run the pipeline.
3. Grade the **four layers independently** (a task can pass some and fail others):
   - **Sel** — did it pick the right base table + columns?
   - **Pat** — is the identified ER pattern the expected one?
   - **Chart** — is the highlighted chart the primary (or an acceptable alternative)?
   - **F/J/A** — is the filter / join / aggregate applied correctly? (the hardest layer)
4. Record P/F (or partial) in the sheet below and note what actually happened.

Suggested headline metrics: **pattern accuracy**, **chart accuracy** (primary or acceptable),
and **end-to-end** (a sensible chart renders). Compare against David's column
(he got 11/13 overall; 4 via point-and-click, 7 needing custom SQL, 2 failed).

## Difficulty tiers

- **Core (should pass on selection+pattern+chart):** D2, D8 (scatter, is-a); D4, D11 (basic bar +
  simple filter); D9 (temporal line); D7, D12 (many-many sankey); D3 (reflexive chord); D13, D10
  (weak entity, before the hard filter).
- **Hard filter/join/aggregate (grade F/J/A separately):** D1, D3, D10, D13 (geographic filter via
  `encompasses`); D4 (top-N); D7 (COUNT=2); D9 (IN + range); D13 (derived speaker threshold).
- **Expected-hard / David failed (graceful degradation is a pass):** D5 (multi-hop join to attribute
  a measure to a country), D6 (temporal MAX 'at some point' + threshold).

## Grading sheet

**Run: full NL mode, live Postgres (same DB as the web), 2026-08-26.** Headline (D5 excluded from
rates as a true n/a): **NL selection 11/13 = 85% · pattern 10/12 = 83% · chart 11/12 = 92%**
(David reference: 11/13, but 7 needed hand-written custom SQL and 2 failed). Artifacts:
`results_pg_full.json`, `run_pg_full.log`. Sel/Pat/Chart are P/F (— = expected-hard, not scored);
F/J/A is what the NL parser actually emitted.

| ID | NL input | Expected (table: cols / pattern / chart) | David | Sel | Pat | Chart | F/J/A emitted (assessment) | Notes on actual result |
|----|----------|------------------------------------------|-------|-----|-----|-------|----------------------------|------------------------|
| D1 | The current population of countries in Europe | country: code,name,population / basic_entity / bar | Pass (p&c) | P | P | P | filter continent=Europe + join encompasses ✓ | Correct end to end. |
| D2 | The relationship between GDP and unemployment for all countries | economy: country,gdp,unemployment / basic_entity_inherited_key / scatter | Pass (p&c) | P | P | P | none ✓ | Scatter (primary). |
| D3 | The length of the borders for all countries in South America | borders: country1,country2,length / reflexive_many_many / chord | Pass (p&c) | P | P | P | filter continent in [S. America] + join encompasses (one side) ~ | Chord/arc/force/matrix. Continent filter applied to one endpoint only. |
| D4 | The top ten Mexican airports by elevation | airport: iata_code,name,elevation / basic_entity / bar | Pass (SQL) | P | P | P | filter country=Mexico ✓ — **no top-N** (order/limit missing) | Bar correct; the "top ten" ordering+limit was not produced. |
| D5 | The GMT offset of all countries | airport: country,gmt_offset / n/a / — | **Fail** | P | — | — | none | **Soft win**: David failed; NL mapped it to airport.gmt_offset+country and drew a bar (did not crash). |
| D6 | All country-city pairs where the population of the city has been at least 5,000,000 at some point | city_population: country,city,year,population / one_many / — | **Fail** | P | F | P (accept) | filter population>=5,000,000 (raw rows, not MAX-over-years) ~ | **Soft win**: David failed; produced grouped/line. Pattern read as weak_entity; "at some point" MAX not modelled. |
| D7 | Countries that are in two continents | encompasses: country,continent,percentage / many_many / sankey | Pass (SQL) | F | P | P (accept) | group_by country HAVING count_distinct(continent)=2 ✓✓ | Excellent: the HAVING aggregate parsed from plain English. Sel F only because `percentage` was not selected. |
| D8 | The relationship between industry and service GDP in the economies of different countries | economy: country,industry,service / basic_entity_inherited_key / scatter | Pass (p&c) | P | P | P | none ✓ | Scatter (primary). |
| D9 | Display the population of France, Spain, and Italy for the years 1960 to 2015 | country_population: country,year,population / weak_entity / line | Pass (SQL) | P | P | P | filter country IN [France,Spain,Italy] + year range 1960–2015 + join country.name ✓✓ | Fully correct incl. both filters. |
| D10 | Display the history of the population level of each country in Oceania | country_population: country,year,population / weak_entity / line | Pass (SQL) | P | P | P | filter continent=Oceania + joins country.name, encompasses.continent ✓ | Line (primary). Extra `country_name` column is harmless. |
| D11 | Display the elevation of all airports that are at least 2000 in altitude | airport: iata_code,elevation / basic_entity / bar | Pass (SQL) | P | P | P | filter elevation>=2000 ✓ | Bar (primary), keyed correctly. |
| D12 | Display how the population of continents is divided between countries | encompasses: country,continent,percentage / many_many / sankey | Pass (SQL) | F | F | F | join encompasses.continent only, no aggregation | **Clean miss**: flattened to country.population bar; lost the part-of-whole many-many relationship. The one fully-wrong task. |
| D13 | The languages spoken in South American countries, excluding languages spoken by less than 1,000,000 people on the continent | spoken: country,name,percentage / weak_entity / grouped bar | Pass (SQL) | P | P | P | filter continent=S. America + joins country.population, encompasses.continent ✓ — **derived speaker threshold not computed** | Grouped bar (primary); geographic filter correct; the cross-table <1M-speakers exclusion was not done. |

### Summary of the F/J/A layer (David's "custom SQL" pain point)

From plain English the NL parser **auto-generated** the query structure for most tasks: geographic
filters via an `encompasses` join (D1/D3/D10/D13), multi-value `IN` + numeric range (D9), and a
`HAVING count_distinct = 2` aggregate (D7) — all cases David needed hand-written SQL for. Gaps: top-N
ordering/limit (D4), temporal MAX framing (D6), a derived cross-table threshold (D13), and the D12
part-of-whole relationship (the only end-to-end miss).

## v2 results (schema-context + self-consistency, 2026-08-26)

Two non-leaking improvements were added to `nlquery/nl_to_selection.py`:
1. **Richer schema context** — each column now carries a semantic badge (num/time/lex/geo, from
   `geodetect`) and the brief ends with an explicit **relationship-table list** ("encompasses connects
   country, continent") derived purely from the FK graph. No pattern/chart labels — blind/gold intact.
2. **Self-consistency** — `parse(samples=N, temperature>0)` runs the parser N times and majority-votes
   on (table, column-set); the modal selection wins. Vote agreement is stored per task.

Run: D1–D8 **reused** from v1 (identical selections; qwen3.7-plus), **D9–D13 re-run on
`qwen3.7-flash`** with the new code, `--samples 5 --temperature 0.7` (the API model was switched to
flash mid-experiment). Artifacts: `results_pg_full_v2.json`, `run_pg_full_v2.log`.

| Metric | v1 (qwen3.7-plus, old parser) | v2 (D1–8 reused + D9–13 flash + new parser) | Δ |
|--------|-------------------------------|---------------------------------------------|---|
| NL selection | 11/13 = 85% | 11/13 = 85% | = |
| Pattern | 10/12 = 83% | **11/12 = 92%** | **+9pt** |
| Chart | 11/12 = 92% | **12/12 = 100%** | **+8pt** |

**What changed:** **D12 fixed** — v1 flattened "how the population of continents is divided between
countries" to a `country.population` bar (basic_entity, chart miss); v2 picks **`encompasses`
(country, continent)** → many_many → chart hit, and even auto-joins `country.population` to weight it.
The relationship-table context surfaced `encompasses`, and voting (3/5 samples agreed on it, over 3
distinct signatures) stabilised the choice. Vote agreement elsewhere: D10 5/5, D9 4/5, D11 3/5, D13 3/5.

**Honest caveats:**
- **Selection stays 85%** because D7 and D12 still miss `percentage` under the strict
  column-superset test — but D12's many-many relationship is now correctly captured (the "fail" is a
  gold-superset artifact, not a wrong chart). D7 was **reused from v1** (old parser, qwen3.7-plus), so
  it was not re-tested with the new schema context; a fresh run might include `percentage`.
- **Mixed models / partial re-run:** D1–D8 are qwen3.7-plus + old parser; only D9–D13 are flash + new
  parser. So the +9/+8pt gain is not a clean single-variable A/B — but D9/D10/D11/D13 were already
  correct in v1 (flash did not regress them), and D12 (re-run) is the net win, mechanistically
  explained by the relationship context + voting. A clean full-flash v2 would re-run D1–D13.

## Reading the results

- If **pattern + chart** are right but **F/J/A** is wrong, that mirrors David's "needs custom SQL"
  outcome — the conceptual recommendation is sound, only the query refinement is missing.
- D5/D6 are the cases David's tool could not do at all; if our LLM path degrades gracefully (or
  honestly reports it cannot map the measure) that is the intended behaviour, not a bug.
- The most interesting wins would be any of the geographic-filter tasks (D1/D3/D10/D13) or the
  aggregate tasks (D7/D6) working end-to-end from plain English, since those are exactly where a
  deterministic point-and-click tool needed hand-written SQL.
