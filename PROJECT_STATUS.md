# Project Status

## Current Stage

Date: 2026-06-09

The project is currently at the stage of testing whether LLMs can accurately identify visualisation schema patterns and then implement visually effective web-based visualisations.

Because API access is not currently available, testing is being carried out manually through the university agent platform using GPT and Claude.

## Current Experimental Workflow

The current workflow has three main steps:

1. Pattern identification
   - The LLM is given a selected Mondial table name and column names.
   - It identifies the ER visualisation schema pattern, such as `basic_entity`, `weak_entity`, `one_many_relationship`, `many_many_relationship`, or `reflexive_many_many_relationship`.

2. Chart selection and mapping
   - The LLM uses the visualisation rules from McBrien and Poulovassilis's work to select suitable chart types for the identified schema pattern.
   - It must also produce an explicit entity-to-chart mapping, such as source, target, weight, key, measure, x/y attributes, or size attributes.

3. Visualisation implementation
   - The LLM is given the selected mapping and the relevant Mondial data.
   - It generates a runnable visualisation implementation, currently as standalone HTML files using libraries such as D3 or Google Charts.

For steps 1 and 2, the LLM is given:

- `experiments/pattern_notes.md`
- `experiments/mondial_database/mondial_schema_summary_clean.json`
- `experiments/prompts/mondial_pattern_prompt.md`

For step 3, the LLM is given:

- `experiments/prompts/visualisation_implementation_prompt.md`
- relevant Mondial data JSON files, such as `mondial_data.json`, `mondial_encompasses_data.json`, or `mondial_country_area.json`

## Recent Repository Updates

The dissertation folder now includes the interim report:

- `dissertation/interim_report.pdf`

The literature folder now includes key background sources:

- Hannan 2024 VizER report
- McBrien and Poulovassilis paper on visualisation based on conceptual modelling and schema transformations

A project description file has also been added:

- `project description.md`

## Today's Work

The current work focused on improving the third stage of the experiment: generating higher-quality visualisations after schema-pattern classification and chart mapping.

Work completed:

- Updated the modified Sankey diagram prompt in `experiments/results/prompt_v4`.
- Tested the revised Sankey prompt on the many-many `encompasses` case.
- Addressed the visual issue where the Kazakhstan-to-Europe link overlapped with many other links in the country-continent Sankey diagram.
- Generalised the Sankey prompt so that it is not only specific to the Mondial dataset, but can be applied to Sankey diagrams for other many-many relationship datasets.
- Added an area-weighted Sankey prompt that considers the `country.area` attribute.
- In the area-weighted design, country-side node sizes and link widths can be based on `area * percentage / 100`, while continent-side node sizes represent total incoming area contribution.
- Added a prompt for reflexive many-many relationships using chord diagrams.
- Tested chord diagram generation for reflexive relationship cases and saved the corresponding visualisation results in `experiments/results/prompt_v4`.

Relevant output location:

- `experiments/results/prompt_v4`

## Current Position

The project is still in the visualisation implementation phase.

The main current focus is no longer only whether the LLM can classify the schema pattern correctly. The current focus is whether the LLM can implement the selected visualisation in a way that is:

- faithful to the schema-pattern mapping
- visually readable
- aesthetically acceptable
- generalisable beyond one specific Mondial case

## Next Planned Work

The next plan is to create more specialised implementation prompts for other ER schema patterns and their corresponding visualisations.

Examples include:

- `basic_entity` with bar charts, scatter charts, bubble charts, calendar charts, choropleth maps, or word clouds
- `weak_entity` with line charts, grouped bar charts, stacked bar charts, or spider/radar charts
- `one_many_relationship` with treemaps, hierarchy trees, or circle packing
- `many_many_relationship` with Sankey diagrams
- `reflexive_many_many_relationship` with chord diagrams or network-style visualisations

The aim is to build a prompt set where each schema pattern and chart type has clearer implementation guidance, rather than relying on one generic visualisation implementation prompt for all chart families.
