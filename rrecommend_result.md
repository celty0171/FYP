case: case 1
table: Country
column: code, population
What the system detected
Schema pattern: Basic entity 246 rows show top 
all
 rows
Recommended charts (click to render): Bar chartChoropleth map ★Word cloud
LLM pick: Choropleth map — Choropleth map efficiently displays population distribution across 246 geographical codes without the clutter of a bar chart.
Choropleth map — Effectively visualizes population across 246 geographical codes without clutter.
Bar chart — Unreadable with 246 distinct categories despite showing all measures.
Word cloud — Less intuitive for spatial data than a map, though conditionally valid.
Mapping for the shown chart:
table
country
region
code
color
population
Each item has more than one key — switch which one labels it (e.g. name vs code).

case: case 2
table:Economy 
columns:country, gdp, inflation
What the system detected
Schema pattern: Basic entity inherited key 246 rows show top 
all
 rows
Recommended charts (click to render): Scatter diagram ★Bar chartChoropleth mapWord cloud
LLM pick: Scatter diagram — Scatter diagram effectively displays both numeric measures against each other while using country as the identifier, satisfying the selection of all columns.
Scatter diagram — Shows all selected measures with country as key, ideal for comparing two numeric variables across 246 entities.
Word cloud — Shows all measures but becomes unreadable with 246 distinct labels and lacks precision for numeric comparison.
Bar chart — Drops the inflation measure, failing to represent the full user selection.
Choropleth map — Drops inflation and relies on unproven geographic mapping capabilities for the given country names.

case: case 3
table:lake
columns: name,elevation,depth,dam_height
What the system detected
Schema pattern: Basic entity 223 rows show top 
all
 rows
Recommended charts (click to render): Scatter diagram ★Bubble chartBar chartWord cloud
LLM pick: Scatter diagram — Scatter diagram effectively displays all three numeric measures across 223 entities without dropping any selected data.
Scatter diagram — Shows all three numeric measures clearly across 223 rows without dropping any selected data.
Bubble chart — Also shows all measures but may suffer from overplotting with 223 points compared to a simple scatter.
Bar chart — Drops two selected numeric measures, limiting analysis to a single attribute.
Word cloud — Conditional and drops a selected measure, making it unsuitable for this numeric-heavy selection.
Mapping for the shown chart:
table
lake
key
name
x
elevation
y
depth
size
dam_height

case: case 4
table: organization
columns: established, abbreviation
What the system detected
Schema pattern: Basic entity 169 rows show top 
all
 rows
Recommended charts (click to render): Calendar chart ★
LLM pick: Calendar chart — The calendar chart maps the establishment date to time and uses the abbreviation as the key, displaying all selected columns effectively.
Calendar chart — Maps the temporal established column to the calendar axis and uses abbreviation as the key, showing all selected data.
Mapping for the shown chart:
table
organization
date
established
key
abbreviation

case: case 5
table: country population
columns: country, year, population
What the system detected
Schema pattern: Weak entity 2278 rows show top 
all
 rows
Recommended charts (click to render): Line chart ★Grouped bar chart
LLM pick: Line chart — Line chart effectively tracks population changes over time across many countries, avoiding the severe overcrowding a bar chart would face with 246 groups.
Line chart — Ideal for temporal trends; handles multiple country series better than categorical grouping.
Grouped bar chart — Unusable with 246 distinct country categories on the grouping axis, causing extreme visual clutter.
Mapping for the shown chart:
table
country_population
series
country
x
year
y
population


case: case 6
table: Ethnic Group
columns: country, name, percentage
What the system detected
Schema pattern: Weak entity 1472 rows show top 
all
 rows
Recommended charts (click to render): Grouped bar chart ★
LLM pick: Grouped bar chart — It maps all three selected columns directly to group, segment, and value roles, fully covering the user's data scope.
Grouped bar chart — Directly maps country, name, and percentage to group, segment, and value, showing all selected measures.
Mapping for the shown chart:
table
ethnic_group
group
country
segment
name
value
percentage


case: case 7
table: Airport
columns: island, iata_code, elevation
What the system detected
Schema pattern: One many relationship 1304 rows show top 
all
 rows
Recommended charts (click to render): Tree map ★Circle packingHierarchy tree
LLM pick: Tree map — Tree map effectively displays the island-airport hierarchy while encoding elevation as area, covering all selected columns.
Tree map — Best fits the hierarchical structure and numeric measure, displaying all selected columns clearly.
Circle packing — Also shows all columns hierarchically but may become visually cluttered with 171 islands.
Hierarchy tree — Drops the selected elevation measure, failing to represent the full user selection.
Mapping for the shown chart:
table
airport
parent
island
child
iata_code
measure
elevation

case: case 8
table: encompasses
columns: country, continent, percentage
What the system detected
Schema pattern: Many many relationship 251 rows show top 
all
 rows
Recommended charts (click to render): Sankey diagram ★Matrix heatmapForce graph
LLM pick: Sankey diagram — Sankey diagrams effectively visualize categorical mappings with a quantitative width, making the country-to-continent relationships and percentages clear.
Sankey diagram — Best fits the categorical mapping and scalar width, providing a clear visual flow.
Matrix heatmap — Shows all measures but becomes unwieldy with 246 rows, reducing readability.
Force graph — Designed for network topology rather than structured categorical data, offering less clarity here.
Mapping for the shown chart:
table
encompasses
source
country
target
continent
width
percentage
pattern
many_many_relationship

case: case 9
table: borders
columns:country1, country2, length
What the system detected
Schema pattern: Reflexive many many relationship 326 rows show top 
all
 rows
Recommended charts (click to render): Chord diagramMatrix heatmapForce graph ★Arc diagram
LLM pick: Force graph — Force graph effectively reveals network topology, clusters, and edge weights for ~169 nodes without the clutter of circular layouts or sparsity issues of matrices.
Force graph — Best for exploring topology, clusters, and hubs in a sparse network of ~169 nodes with weighted edges.
Matrix heatmap — Effective for exact pairwise values but becomes sparse and hard to parse at 169x169 without manual reordering.
Chord diagram — Visually appealing for flows, but 169 nodes cause significant label overlap and ribbon clutter despite low density.
Arc diagram — Useful for ordered sequences, but lacks a natural ordering for countries and struggles with cross-axis link visibility.
Mapping for the shown chart:
table
borders
source
country1
target
country2
value
length
pattern
reflexive_many_many_relationship