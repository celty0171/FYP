-- A deliberately NON-Mondial database, to test the "new user connects their own DB" path.
-- Different table/column names from Mondial on purpose, but exercises every generalisation:
--   * nation      : basic_entity; key is an ISO alpha-3 code (geographical via the new iso tokens),
--                   nation_name is a country name (geographical + lexical, matches the world basemap
--                   -> choropleth should RENDER, not be hidden). population/gdp_usd_bn are scalars.
--   * warehouse   : one_many (FK to nation); its readable column is `label`, NOT `name`
--                   -> tests the generalised _label_col (labels beyond Mondial's `name`).
--   * shipment    : one_many (FK to warehouse); ship_date (temporal) + weight/value (scalars)
--                   -> line / scatter / calendar candidates.
--
-- Load into a FRESH database (see the commands in chat), then connect the web app to it.

DROP TABLE IF EXISTS shipment, warehouse, nation CASCADE;

CREATE TABLE nation (
    iso3        CHAR(3)      PRIMARY KEY,        -- ISO alpha-3 (geographical)
    nation_name VARCHAR(80)  NOT NULL UNIQUE,    -- country name (geographical + lexical, alt key)
    population  BIGINT,
    gdp_usd_bn  NUMERIC
);

CREATE TABLE warehouse (
    id          INTEGER      PRIMARY KEY,
    label       VARCHAR(80)  NOT NULL,           -- readable label (NOT called "name")
    iso3        CHAR(3)      REFERENCES nation(iso3),
    capacity_m3 NUMERIC,
    opened_on   DATE
);

CREATE TABLE shipment (
    id           INTEGER     PRIMARY KEY,
    warehouse_id INTEGER     REFERENCES warehouse(id),
    ship_date    DATE,
    weight_kg    NUMERIC,
    value_usd    NUMERIC
);

INSERT INTO nation (iso3, nation_name, population, gdp_usd_bn) VALUES
 ('USA','United States',331000000,25460),
 ('CHN','China',1412000000,17960),
 ('DEU','Germany',83200000,4070),
 ('JPN','Japan',125700000,4230),
 ('BRA','Brazil',214300000,1920),
 ('IND','India',1408000000,3390),
 ('GBR','United Kingdom',67300000,3070),
 ('FRA','France',67750000,2780),
 ('CAN','Canada',38250000,2140),
 ('AUS','Australia',25690000,1550);

INSERT INTO warehouse (id, label, iso3, capacity_m3, opened_on) VALUES
 (1,'Chicago Hub','USA',120000,'2015-03-01'),
 (2,'Shanghai Port','CHN',200000,'2012-07-15'),
 (3,'Berlin Depot','DEU',80000,'2018-01-20'),
 (4,'Osaka Centre','JPN',95000,'2016-11-05'),
 (5,'Sao Paulo Yard','BRA',60000,'2019-06-30'),
 (6,'Mumbai Store','IND',110000,'2017-02-14'),
 (7,'London Cross','GBR',75000,'2014-09-01'),
 (8,'Lyon Depot','FRA',70000,'2018-08-22');

INSERT INTO shipment (id, warehouse_id, ship_date, weight_kg, value_usd) VALUES
 (1,1,'2023-01-10',1200,45000),
 (2,1,'2023-02-14', 800,31000),
 (3,2,'2023-01-22',2400,88000),
 (4,2,'2023-03-03',1900,72000),
 (5,3,'2023-02-01', 600,21000),
 (6,4,'2023-02-19', 950,35000),
 (7,5,'2023-03-11',1500,50000),
 (8,6,'2023-01-30',1750,61000),
 (9,7,'2023-02-27', 700,26000),
 (10,8,'2023-03-18',1100,40000);
