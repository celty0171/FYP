# ER Schema Pattern Design Notes

## DATA-FIRST Pattern Identification

This system identifies the visualisation schema pattern from a user's selected columns in two stages.

1. Analyse selected primary-key and foreign-key columns to identify the ER schema pattern.
2. Analyse all selected columns and their SQL data types to recommend chart types inside that pattern's visualisation group.

## Pattern Rules

### Basic Entity

A selected table is a basic entity when the selected columns contain a primary key and attributes without a selected foreign-key dependency.

We also classify an inherited-key table as a basic entity when the whole primary key is inherited as a foreign key from one parent entity and there is no local primary-key column. Example: `economy.country`. Also attributes of the parent table can be regarded as also attributes of the inhertied-key table. Note each inherited-key entity has only one instance for each instance of the parent entity.

### Weak Entity

A weak entity has a compound primary key where a proper subset of the key is a foreign key to a single parent entity and at least one remaining primary-key column is local to the child entity.

This is the main boundary with inherited-key basic entities: if every primary-key column is also a foreign key, the table is inherited-key basic; if the primary key combines foreign-key columns with local child key columns, the table is weak.

Do not classify a weak entity as a one-many relationship merely because it has a parent foreign key. In this pattern, the parent foreign key is part of the weak entity's primary key, and the remaining primary-key column identifies the child instance within the parent.

### One-Many Relationship

A one-many pattern is identified when the selected columns contain a single foreign key to a single parent entity, and that foreign key is not part of the table's primary key.

Do not classify a one-many selection as a basic entity merely because the child table has its own primary key and scalar attributes. If the selected columns include a foreign key outside the primary key, the selected data expresses a parent-child link. 

### Many-Many Relationship

A many-many relationship is represented by a relationship table whose primary key is composed of two foreign keys to two separate parent tables.

### Reflexive Many-Many Relationship

A reflexive many-many relationship is a special many-many case where both foreign keys reference the same parent table.

## Chart Recommendation Groups

The chart recommendation step must not merely list all charts in a pattern group. It must check each chart's mandatory requirements against the selected columns, then choose the best supported chart(s) and state the exact schema-to-chart mapping.

### Basic Entity

The basic entity pattern applies when instances of one entity `E` are identified by a key `k` and described by attributes `a1`, `a2`, etc.

- Bar chart: use when the selected entity has a key `k` and at least one scalar attribute `a1`. Each instance of `E`, identified by `k`, is represented as a bar. The length of the bar is determined by `a1`, so `a1` should be numeric or otherwise scalar.

- Calendar chart: use when the selected entity has a date-valued attribute `a1`. Each instance of `E` is represented according to that date attribute. Optional `a2` may colour the calendar entry.

- Scatter diagram: use when the selected entity has two scalar attributes `a1` and `a2`. Each instance of `E` is represented as a point. Attribute `a1` maps to the x coordinate and `a2` maps to the y coordinate. A third attribute `a3` may optionally be used to colour the point.

- Bubble chart: use when the selected entity has at least three scalar attributes `a1`, `a2`, and `a3`. Each instance of `E` is represented as a bubble. Attributes `a1` and `a2` define the bubble coordinates, while `a3` determines bubble size. A fourth attribute `a4` may optionally be used to colour the bubble.

- Choropleth map: use when key `k` can be interpreted as a geographical region, and scalar or colourable attribute `a1` maps to region colour.

- Word cloud: use when key `k` can be interpreted as words or lexical labels, and scalar attribute `a1` maps to word size. Optional `a2` may map to colour.

Basic entity mapping variables:

- `E`: selected entity table.
- `k`: entity key, usually the primary key or inherited key.
- `a1`, `a2`, `a3`, `a4`: selected attributes, usually scalar/temporal/geographical/lexical depending on chart requirements.

### Weak Entity

The weak entity pattern applies when an entity has a compound key made from a parent key `k1` and a local child key `k2`, plus attributes such as `a1`. The values of `k2` should lie within a similar range for all values of `k1`, otherwise comparison in one chart is not meaningful. Some charts also require completeness: each value of `k1` should have the same, or almost the same, set of `k2` values.

- Line chart: use when each distinct value of parent key `k1` should be represented as a separate line. The child key `k2` should be a scalar dimension plotted on the x-axis, and scalar attribute `a1` should be plotted on the y-axis. XY variants may add another scalar attribute `a2` to the y-axis.

- Stacked bar chart: use when each distinct value of parent key `k1` should be represented as a bar, with each stacked element representing a value of child key `k2`. Scalar attribute `a1` determines the length of the stacked elements. This chart requires completeness, because each `k1` bar should contain the same, or almost the same, set of `k2` values so that the stacks are comparable.

- Spider chart: use when each ring represents a value of parent key `k1`, each spoke represents a value of child key `k2`, and the intersection of a ring and spoke is determined by attribute `a1`. This is suitable when the weak entity supports meaningful comparison of `a1` across the `k2` values for each `k1`.

Weak entity mapping variables:

- `k1`: parent key, i.e. the foreign-key portion of the weak entity primary key.
- `k2`: local child key, i.e. the non-foreign-key portion of the weak entity primary key.
- `a1`: scalar measure attribute of the weak entity.
- `a2`: optional additional scalar measure for line chart variants.

Mandatory checks:

- Line chart requires scalar `k2` for the x-axis and scalar `a1` for the y-axis.
- Stacked bar, grouped bar, and spider charts require scalar `a1`.
- Stacked bar and spider chart work best when `k2` values are complete or nearly complete across `k1` values.

### One-Many Relationship

The one-many relationship pattern applies to hierarchical data where a parent entity `Ep` is connected to a child entity `Ec`. In this pattern, instances of `Ep` organise or contain instances of `Ec`.

- Tree map: use when instances of parent entity `Ep` should be represented as rectangles that are divided into rectangles for child instances `Ec`. A scalar attribute `a1` determines the area of each child rectangle. Additional scalar attributes `a2`, `a3`, etc. may be offered through a selector to change which measure controls the area.

- Hierarchy tree: use when instances of parent entity `Ep` should be shown as nodes connected by lines to child instances `Ec`. A discrete attribute `a1` may optionally be used to colour the links between the entities.

- Circle packing: use when instances of parent entity `Ep` should be represented as circles containing circles for child instances `Ec`. Scalar attribute `a1` determines the area of child circles. Optional `a2` may colour child circles.

One-many mapping variables:

- `Ep`: parent entity referenced by the selected non-primary foreign key.
- `Ec`: selected child entity table.
- `kp`: parent key, the selected foreign-key column(s) in `Ec`.
- `kc`: child key, normally the primary key of `Ec`.
- `a1`: scalar measure attribute on `Ec` for treemap/circle-packing area.
- `a2`: optional colour attribute.

Mandatory checks:

- Treemap and circle packing require a scalar `a1` on child instances.
- Hierarchy tree does not require scalar size, but may use a discrete attribute for colour.

### Many-Many Relationship

The many-many relationship pattern applies when a relationship connects instances of entity `E1` and entity `E2`. The data that governs the visualisation is stored as attributes of the relationship between the entities.

- Sankey diagram: use when the left-hand elements should represent instances of `E1`, the right-hand elements should represent instances of `E2`, and a scalar relationship attribute `a1` should determine the width of the flow between them. A second relationship attribute `a2` may optionally be represented by colour.

- Chord diagram: use when instances of the entities should be represented as points around the perimeter of a circle, and a scalar relationship attribute `a1` should determine the width of the connection between pairs of points. A second relationship attribute `a2` may optionally be represented by colour.

Many-many mapping variables:

- `E1`: first parent entity referenced by the relationship table.
- `E2`: second parent entity referenced by the relationship table.
- `k1`: relationship-table foreign key to `E1`.
- `k2`: relationship-table foreign key to `E2`.
- `R`: relationship table.
- `a1`: scalar relationship attribute used as link/flow weight.
- `a2`: optional relationship attribute used for colour.

Mandatory checks:

- Sankey requires non-reflexive `E1 -> E2` links and scalar `a1` for flow width. 
- Chord requires scalar `a1` for connection width and is especially suitable for reflexive relationships, though it can also represent non-reflexive many-many links if the library supports grouping entity types.

### Reflexive Many-Many Relationship

The reflexive many-many relationship pattern is a special many-many case where the relationship connects instances of the same entity type `E` to other instances of `E`.

- Chord diagram: use especially for reflexive many-many relationships. In this case, all points around the circle represent instances of the same entity type `E`, rather than being grouped into two different entity types, and the connections show relationships between pairs of instances.

Reflexive many-many mapping variables:

- `E`: the single parent entity type referenced by both relationship foreign keys.
- `k1`, `k2`: two foreign keys to the same entity type.
- `R`: reflexive relationship table.
- `a1`: scalar relationship attribute used as connection width.
- `a2`: optional relationship attribute used for colour.
