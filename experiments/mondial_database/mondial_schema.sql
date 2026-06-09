-- XMLSQL log file mondial_schema.sql of executed statements

-- country
CREATE TABLE country
(name VARCHAR(32) NOT NULL CONSTRAINT country_name_ck UNIQUE,
 code VARCHAR(4) CONSTRAINT country_pk PRIMARY KEY,
 capital VARCHAR(35) NULL,
 province VARCHAR(32) NULL,
 area NUMERIC(10,2) NOT NULL 
 CONSTRAINT country_area_range CHECK (area >= 0),
 population INTEGER NOT NULL
 CONSTRAINT country_population_range CHECK (population >= 0));

-- country_population
CREATE TABLE country_population (
 country VARCHAR(4), --CONSTRAINT country_population_of REFERENCES country,
 year INT CONSTRAINT country_population_year CHECK (year >= 0),
 population INT NOT NULL
 CONSTRAINT country_population_population CHECK (population >= 0),
 CONSTRAINT country_population_pk PRIMARY KEY (country,year));

-- province
CREATE TABLE province
(name VARCHAR(48) CONSTRAINT province_name NOT NULL,
 country  VARCHAR(4) CONSTRAINT province_country NOT NULL,
 population INTEGER CONSTRAINT province_population_range
            CHECK (population >= 0) NULL,
 area INTEGER CONSTRAINT province_area_range CHECK (area >= 0) NULL,
 capital VARCHAR(50),
 capital_province VARCHAR(48),
 CONSTRAINT province_pk PRIMARY KEY (name, country),
 CONSTRAINT province_country_we FOREIGN KEY (country) REFERENCES country);

-- province_population
CREATE TABLE province_population
(province VARCHAR(48),
 country VARCHAR(4),
 year INT CONSTRAINT province_population_year_range
   CHECK (year>=0),
 population DECIMAL CONSTRAINT province_population_population_range
   CHECK (population>=0) NOT NULL,
 CONSTRAINT province_population_pk PRIMARY KEY (country, province, year),
 CONSTRAINT province_population_we FOREIGN KEY (province, country)
            REFERENCES province);

-- province_other_name
CREATE TABLE province_other_name
(province VARCHAR(48),
 country VARCHAR(4),
 other_name VARCHAR(48),
 CONSTRAINT province_other_name_pk PRIMARY KEY (country, province, other_name),
 CONSTRAINT province_other_name_mva FOREIGN KEY (province, country)
            REFERENCES province);

-- province_local_name
CREATE TABLE province_local_name
(province VARCHAR(48),
 country VARCHAR(4),
 local_name VARCHAR(90),
 CONSTRAINT province_local_name_pk PRIMARY KEY (country, province),
 CONSTRAINT province_local_name_isa FOREIGN KEY (province, country)
            REFERENCES province);

-- country_other_name
CREATE TABLE country_other_name
(country VARCHAR(4),
 other_name VARCHAR(48),
 CONSTRAINT country_other_name_pk PRIMARY KEY (country, other_name),
 CONSTRAINT country_other_name_mva FOREIGN KEY (country)
            REFERENCES country);

-- country_local_name
CREATE TABLE country_local_name
(country VARCHAR(4) NOT NULL,
 local_name VARCHAR(120) NOT NULL,
 CONSTRAINT country_local_name_pk PRIMARY KEY (country),
 CONSTRAINT country_local_name_oa FOREIGN KEY (country)
            REFERENCES country);

-- population
CREATE TABLE population
(country VARCHAR(4) CONSTRAINT population_pk PRIMARY KEY,
 population_growth NUMERIC(5,2),
 infant_mortality NUMERIC(5,2),
 CONSTRAINT population_isa FOREIGN KEY (country) REFERENCES country);

-- politics
CREATE TABLE politics
(country VARCHAR(4) CONSTRAINT politics_pk PRIMARY KEY,
 independence DATE,
 was_dependent VARCHAR(32),  -- was 50
 dependent VARCHAR(4) NULL,
 government VARCHAR(120),
 CONSTRAINT politics_isa FOREIGN KEY (country) REFERENCES country);

-- economy
CREATE TABLE economy
(country VARCHAR(4) CONSTRAINT economy_pk PRIMARY KEY,
 gdp INT CONSTRAINT economy_gdp CHECK (gdp>=0),
 agriculture NUMERIC(5,2),
 service NUMERIC(5,2),
 industry NUMERIC(5,2),
 inflation NUMERIC(5,2),
 unemployment NUMERIC(5,2),
 CONSTRAINT economy_isa FOREIGN KEY (country) REFERENCES country);

-- language
CREATE TABLE language
(name VARCHAR(50),
 super_language VARCHAR(50) NULL,
 CONSTRAINT language_pk PRIMARY KEY (name),
 CONSTRAINT language_super_language_fk FOREIGN KEY (super_language) REFERENCES language);

-- spoken
CREATE TABLE spoken
(country VARCHAR(4),
 name VARCHAR(50),
 percentage NUMERIC(4,1) NULL  
 CONSTRAINT spoken_percent_range CHECK (percentage BETWEEN 0 AND 100),
 CONSTRAINT spoken_pk PRIMARY KEY (name, country),
 CONSTRAINT spoken_of_we FOREIGN KEY (country) REFERENCES country);

-- ethnic group
CREATE TABLE ethnic_group
(country VARCHAR(4),
 name VARCHAR(50),
 percentage DECIMAL NULL
 CONSTRAINT ethnic_group_percent_range CHECK (percentage BETWEEN 0 AND 100),
 CONSTRAINT ethnic_group_pk PRIMARY KEY (name, country),
 CONSTRAINT ethnic_group_of_we FOREIGN KEY (country) REFERENCES country);

-- religion
CREATE TABLE Religion
(country VARCHAR(4),
 name VARCHAR(50),
 percentage DECIMAL NOT NULL
 CONSTRAINT religion_percent_range CHECK (percentage BETWEEN 0 AND 100),
 CONSTRAINT religion_pk PRIMARY KEY (name, country),
 CONSTRAINT religion_of_we FOREIGN KEY (country) REFERENCES country);

-- city
CREATE TABLE city
(name VARCHAR(48) NOT NULL,
 country VARCHAR(4) NOT NULL,
 province VARCHAR(48) NOT NULL,
 population DECIMAL NULL,
 CONSTRAINT city_population_range CHECK (population>=0),
 latitude NUMERIC(5,2) NOT NULL
 CONSTRAINT city_latitude_range CHECK (latitude BETWEEN -90 AND 90),
 longitude NUMERIC(5,2) NOT NULL 
 CONSTRAINT city_longtitude_range CHECK (longitude BETWEEN -180 AND 180),
 elevation INTEGER,
 CONSTRAINT city_pk PRIMARY KEY (name, province, country),
 CONSTRAINT city_province_we FOREIGN KEY (province, country)
            REFERENCES province);

-- city_population
CREATE TABLE city_population
(city VARCHAR(48),
 country VARCHAR(4),
 province VARCHAR(48),
 year DECIMAL CONSTRAINT city_population_year_range CHECK (year>=0),
 population DECIMAL CONSTRAINT city_population_population_range
            CHECK (population>=0) NOT NULL,
 CONSTRAINT city_population_pk PRIMARY KEY (country, province, city, year),
 CONSTRAINT city_population_we 
            FOREIGN KEY (city, province, country) REFERENCES city);

-- city_other_name
CREATE TABLE city_other_name
(city VARCHAR(48),
 country VARCHAR(4),
 province VARCHAR(48),
 other_name VARCHAR(50),
 CONSTRAINT city_other_name_pk
            PRIMARY KEY (country, province, city, other_name),
 CONSTRAINT city_other_name_mva 
            FOREIGN KEY (city, province, country) REFERENCES city);

-- city_local_name
CREATE TABLE city_local_name
(city VARCHAR(50),
 country VARCHAR(4),
 province VARCHAR(48),
 local_name VARCHAR(48),
 CONSTRAINT city_local_name_pk PRIMARY KEY (country, province, city),
 CONSTRAINT city_local_name_isa 
            FOREIGN KEY (city, province, country) REFERENCES city);

-- continent
CREATE TABLE continent
(name VARCHAR(20) CONSTRAINT continent_pk PRIMARY KEY,
 area NUMERIC(10,2) NOT NULL);

-- borders
CREATE TABLE borders
(country1 VARCHAR(4) CONSTRAINT border_country_a_fk REFERENCES country,
 country2 VARCHAR(4) CONSTRAINT border_country_b_fk REFERENCES country,
 length NUMERIC(10,2) NOT NULL CONSTRAINT border_length CHECK (length > 0),
 CONSTRAINT border_pk PRIMARY KEY (country1,country2) );

-- encompasses
CREATE TABLE encompasses
(country VARCHAR(4) NOT NULL 
 CONSTRAINT encompasses_country_fk REFERENCES country,
 continent VARCHAR(20) NOT NULL 
 CONSTRAINT encompasses_continent_fk REFERENCES continent,
 percentage NUMERIC(10,2) NOT NULL 
 CONSTRAINT encompasses_percentage_range CHECK (percentage BETWEEN 0 AND 100),
 CONSTRAINT encompasses_pk PRIMARY KEY (country,continent));

-- organization
CREATE TABLE organization
(abbreviation VARCHAR(12) CONSTRAINT organization_pk PRIMARY KEY,
 name VARCHAR(100) NOT NULL CONSTRAINT organization_name_ck UNIQUE,
 city VARCHAR(35) NULL,
 country VARCHAR(4) NULL,
 -- CONSTRAINT organization_country_fk REFERENCES country, 
 province VARCHAR(32) NULL,
 established DATE NULL,
 CONSTRAINT city_local_name_fk 
            FOREIGN KEY (city, province, country) REFERENCES city);

-- is_member
CREATE TABLE is_member
(country VARCHAR(4) CONSTRAINT is_member_country_fk REFERENCES country,
 organization VARCHAR(12) 
 CONSTRAINT is_member_organization_fk REFERENCES organization,
 type VARCHAR(64) NOT NULL DEFAULT 'member',
 CONSTRAINT is_member_pk PRIMARY KEY (country,organization) );

-- mountain
CREATE TABLE mountain
(name VARCHAR(32) CONSTRAINT mountain_pk PRIMARY KEY,
 mountains VARCHAR(50),
 elevation NUMERIC(10,2) NOT NULL, 
 type VARCHAR(10),
 CONSTRAINT mountain_elevation_range CHECK (elevation>=0),
 latitude NUMERIC(4,1) NOT NULL
 CONSTRAINT mountain_latitude_range CHECK (latitude BETWEEN -90 AND 90),
 longitude NUMERIC(4,1) NOT NULL 
 CONSTRAINT mountain_longtitude_range CHECK (longitude BETWEEN -180 AND 180));

-- desert
CREATE TABLE desert
(name VARCHAR(25) CONSTRAINT desert_pk PRIMARY KEY,
 area NUMERIC(10,2) NOT NULL,
 latitude NUMERIC(4,1) NULL
 CONSTRAINT desert_latitude CHECK (latitude BETWEEN -90 AND 90),
 longitude NUMERIC(4,1) NULL 
 CONSTRAINT desert_longtitude CHECK (longitude BETWEEN -180 AND 180));

-- island
CREATE TABLE  island
(name VARCHAR(32) CONSTRAINT island_pk PRIMARY KEY,
 islands VARCHAR(32) NULL,
 area NUMERIC(10,2) NULL CONSTRAINT island_area
  CHECK (area BETWEEN 0 AND 2175600),
 elevation INTEGER NULL,
 type VARCHAR(12),
 latitude NUMERIC(4,1) NULL 
 CONSTRAINT island_latitude CHECK (latitude BETWEEN -90 AND 90),
 longitude NUMERIC(4,1) NULL 
 CONSTRAINT island_longtitude CHECK (longitude BETWEEN -180 AND 180));

-- airport
CREATE TABLE airport
(iata_code VARCHAR(3) CONSTRAINT airport_pk PRIMARY KEY,
 name VARCHAR(100),
 country VARCHAR(4),
 city VARCHAR(48),
 province VARCHAR(48),
 island VARCHAR(50) NULL
 CONSTRAINT airport_on_island_fk REFERENCES island(name) ON UPDATE CASCADE,
 latitude NUMERIC(5,2) NOT NULL
 CONSTRAINT airport_latitude_range CHECK (latitude BETWEEN -90 AND 90),
 longitude NUMERIC(5,2) NOT NULL 
 CONSTRAINT airport_longtitude_range CHECK (longitude BETWEEN -180 AND 180),
 elevation INTEGER NULL,
 gmt_offset INTEGER NOT NULL,
 CONSTRAINT airport_city_fk 
 FOREIGN KEY (city, province, country) REFERENCES city);

-- sea
CREATE TABLE sea
(name VARCHAR(32) CONSTRAINT sea_pk PRIMARY KEY,
 area INTEGER NULL CONSTRAINT sea_area CHECK (area>=0),
 depth INTEGER NULL CONSTRAINT sea_depth CHECK (depth>=0));

-- lake
CREATE TABLE lake
(name VARCHAR(32) CONSTRAINT lake_pk PRIMARY KEY,
 river VARCHAR(32) NULL,
 area INTEGER NOT NULL CONSTRAINT lake_area CHECK (area>=0),
 elevation INTEGER NULL,
 depth INTEGER NULL CONSTRAINT lake_depth CHECK (depth>=0),
 dam_height INTEGER NULL CONSTRAINT lake_dam_height CHECK (dam_height>=0),
 type VARCHAR(12),
 latitude NUMERIC(5,2) NOT NULL
 CONSTRAINT lake_latitude CHECK (latitude BETWEEN -90 AND 90),
 longitude NUMERIC(5,2) NOT NULL 
 CONSTRAINT lake_longtitude CHECK (longitude BETWEEN -180 AND 180)
 );

-- river
CREATE TABLE river
(name VARCHAR(32) CONSTRAINT river_pk PRIMARY KEY,
 river VARCHAR(32) NULL CONSTRAINT tributary_to REFERENCES river,
 lake VARCHAR(32) NULL CONSTRAINT river_lake_fk REFERENCES lake,
 sea VARCHAR(32) NULL CONSTRAINT river_sea_fk REFERENCES sea,
 length NUMERIC(10,2) CONSTRAINT river_length_range CHECK (length>=0),
 area DECIMAL CONSTRAINT river_area_range
   CHECK (area >= 0),
 source_latitude NUMERIC(5,2) NOT NULL
 CONSTRAINT source_latitude_range CHECK (source_latitude BETWEEN -90 AND 90),
 source_longitude NUMERIC(5,2) NOT NULL 
 CONSTRAINT source_longtitude_range CHECK (source_longitude BETWEEN -180 AND 180),
 mountains VARCHAR(50),
 source_elevation DECIMAL,
 estuary_latitude NUMERIC(5,2) NOT NULL
 CONSTRAINT estuary_latitude_range CHECK (estuary_latitude BETWEEN -90 AND 90),
 estuary_longitude NUMERIC(5,2) NOT NULL 
 CONSTRAINT estuary_longtitude_range CHECK (estuary_longitude BETWEEN -180 AND 180),
 estuary_elevation DECIMAL,
 CONSTRAINT river_flows_into 
     CHECK ((river IS NULL AND lake IS NULL)
            OR (river IS NULL AND sea IS NULL)
            OR (lake IS NULL AND sea is NULL)));

-- river_through
CREATE TABLE river_through
(river VARCHAR(32) REFERENCES river,
 lake  VARCHAR(32) REFERENCES lake,
 CONSTRAINT river_through_pk PRIMARY KEY (lake) );

-- geo_mountain
CREATE TABLE geo_mountain
(mountain VARCHAR(32) CONSTRAINT geo_mountain_mountain_fk REFERENCES mountain,
 country VARCHAR(4),
 province VARCHAR(48) NOT NULL,
 CONSTRAINT geo_mountain_pk PRIMARY KEY (province,country,mountain),
 CONSTRAINT geo_mountain_province_fk FOREIGN KEY (province,country)
            REFERENCES province);

-- geo_desert
CREATE TABLE geo_desert
(desert VARCHAR(32) CONSTRAINT geo_desert_desert_fk REFERENCES desert,
 country VARCHAR(4),
 province VARCHAR(32) NOT NULL,
 CONSTRAINT geo_desert_pk PRIMARY KEY (province, country, desert),
 CONSTRAINT geo_desert_province_fk FOREIGN KEY (province,country)
            REFERENCES province);

-- geo_island
CREATE TABLE geo_island
(island VARCHAR(32)
 CONSTRAINT geo_island_island_fk REFERENCES island ON UPDATE CASCADE, 
 country VARCHAR(4) CONSTRAINT geo_island_country_fk REFERENCES country,
 province VARCHAR(48) NOT NULL,
 CONSTRAINT geo_island_pk PRIMARY KEY (province, country, island),
 CONSTRAINT geo_island_province_fk FOREIGN KEY (province,country)
            REFERENCES province);

-- geo_river
CREATE TABLE geo_river
(river VARCHAR(32) CONSTRAINT geo_river_river_fk REFERENCES river, 
 country VARCHAR(4), -- CONSTRAINT geo_river_country_fk REFERENCES country,
 province VARCHAR(48) NOT NULL,
 CONSTRAINT geo_river_pk PRIMARY KEY (province,country, river),
 CONSTRAINT geo_island_province_fk FOREIGN KEY (province,country)
            REFERENCES province);

-- geo_sea
CREATE TABLE geo_sea
(sea VARCHAR(32) CONSTRAINT geo_sea_sea_fk REFERENCES sea,
 country VARCHAR(4),
 province VARCHAR(48) NOT NULL,
 CONSTRAINT geo_sea_pk PRIMARY KEY (province, country, sea),
 CONSTRAINT geo_sea_province_fk FOREIGN KEY (province,country)
            REFERENCES province);

-- geo_lake
CREATE TABLE geo_lake
(lake VARCHAR(32) CONSTRAINT geo_lake_lake_fk REFERENCES lake,
 country VARCHAR(4),
 province VARCHAR(48) NOT NULL,
 CONSTRAINT geo_lake_pk PRIMARY KEY (province, country, lake),
 CONSTRAINT geo_lake_province_fk FOREIGN KEY (province,country)
            REFERENCES province);

-- geo_estuary
CREATE TABLE geo_estuary
(river VARCHAR(32) CONSTRAINT geo_estuary_river_fk REFERENCES river,
 country VARCHAR(4),
 province VARCHAR(48),
 CONSTRAINT geo_estuary_pk PRIMARY KEY (province, country, river),
 CONSTRAINT geo_estuary_province_fk FOREIGN KEY (province,country)
            REFERENCES province);

-- geo_source
CREATE TABLE geo_source
(river VARCHAR(32) CONSTRAINT geo_source_river_fk REFERENCES river,
 country VARCHAR(4),
 province VARCHAR(48),
 CONSTRAINT geo_source_pk PRIMARY KEY (province, country, river),
 CONSTRAINT geo_source_province_fk FOREIGN KEY (province,country)
            REFERENCES province);

-- merges_with
CREATE TABLE merges_with
(sea1 VARCHAR(32) CONSTRAINT merges_with_sea_a_fk REFERENCES sea,
 sea2 VARCHAR(32) CONSTRAINT merges_with_sea_b_fk REFERENCES sea,
 CONSTRAINT merges_with_pk PRIMARY KEY (sea1,sea2) );

-- located
CREATE TABLE located
(city VARCHAR(35) NOT NULL, 
 province VARCHAR(48) NOT NULL,
 country VARCHAR(4) NOT NULL,
 river VARCHAR(32) NULL CONSTRAINT located_river_fk REFERENCES river,
 lake VARCHAR(32) NULL CONSTRAINT located_lake_fk REFERENCES lake,
 sea VARCHAR(32) NULL CONSTRAINT located_sea_fk REFERENCES sea,
 CONSTRAINT located_fk 
            FOREIGN KEY (city, province, country) REFERENCES city
 --CONSTRAINT located_pk PRIMARY KEY (city,country)
);

-- located_on
CREATE TABLE located_on
(city VARCHAR(35) NOT NULL, 
 province VARCHAR(48) NOT NULL,
 country VARCHAR(4) NOT NULL,
 island VARCHAR(32) NOT NULL CONSTRAINT located_on_island_fk REFERENCES island,
 CONSTRAINT located_on_pk PRIMARY KEY (city,province,country,island),
 CONSTRAINT located_on_city_fk
            FOREIGN KEY (city, province, country) REFERENCES city
);

-- located fks
-- ALTER TABLE located 
-- ADD CONSTRAINT located_geo_river FOREIGN KEY (province, country, river) 
-- REFERENCES geo_river(province, country, river);
 
-- ALTER TABLE located 
-- ADD CONSTRAINT located_geo_lake FOREIGN KEY (province, country, lake) 
-- REFERENCES geo_lake(province, country, lake);

-- ALTER TABLE located 
-- ADD CONSTRAINT located_geo_sea FOREIGN KEY (province, country, sea) 
-- REFERENCES geo_sea(province, country, sea);

-- island_in
CREATE TABLE island_in
(island VARCHAR(32) CONSTRAINT island_in_island_fk REFERENCES island ON UPDATE CASCADE,
 sea VARCHAR(50) CONSTRAINT island_in_sea_fk REFERENCES sea,
 lake VARCHAR(32) CONSTRAINT island_in_lake_fk REFERENCES lake,
 river VARCHAR(32) CONSTRAINT island_in_river_fk REFERENCES river
);

-- mountain_on_island
CREATE TABLE mountain_on_island
(mountain VARCHAR(50) NOT NULL,
 CONSTRAINT mountain_on_island_mountain_fk FOREIGN KEY (mountain)
 REFERENCES mountain,
 island VARCHAR(32) NOT NULL,
 CONSTRAINT mountain_on_island_island_fk FOREIGN KEY (island)
 REFERENCES island ON UPDATE CASCADE,
 CONSTRAINT mountain_on_island_pk PRIMARY KEY (mountain));

-- lake_on_island
CREATE TABLE lake_on_island
(lake    VARCHAR(32),
 CONSTRAINT lake_on_island_lake_fk FOREIGN KEY (lake)
 REFERENCES lake,
 island  VARCHAR(32),
 CONSTRAINT lake_on_island_island_fk FOREIGN KEY (island)
 REFERENCES island,
 CONSTRAINT lake_on_island_pk PRIMARY KEY (lake));

-- river_on_island
CREATE TABLE river_on_island
(river   VARCHAR(32),
 CONSTRAINT river_on_island_river_fk FOREIGN KEY (river)
 REFERENCES river,
 island  VARCHAR(32),
 CONSTRAINT river_on_island_island_fk FOREIGN KEY (island)
 REFERENCES island,
 CONSTRAINT river_on_island_pk PRIMARY KEY (river));

-- ws_country
CREATE VIEW ws_country AS
SELECT name, code, capital, area, population
FROM country 
WHERE code IN ('AUS','NZ','USA','N','S','IS','DK','SF','DK','FL','CH');

-- ws_organisation
CREATE VIEW ws_organization AS
SELECT abbreviation, city, established
FROM  organization
WHERE organization.abbreviation IN ('EFTA','NC','ANZUS','NATO');

-- ws_encompasses
CREATE VIEW ws_encompasses AS
SELECT *
FROM encompasses
WHERE encompasses.country IN 
     (SELECT ws_country.code 
      FROM   ws_country);

-- ws_is_member
CREATE VIEW ws_is_member AS
SELECT country,organization
FROM is_member
WHERE is_member.country IN 
     (SELECT ws_country.code 
      FROM   ws_country)
AND   organization IN
     (SELECT ws_organization.abbreviation 
      FROM  ws_organization);

-- ws_located
CREATE VIEW ws_located AS
SELECT *
FROM located
WHERE located.country IN 
     (SELECT ws_country.code 
      FROM   ws_country);

-- lab user
GRANT SELECT ON ws_located TO lab;
GRANT SELECT ON ws_is_member TO lab;
GRANT SELECT ON ws_encompasses TO lab;
GRANT SELECT ON ws_country TO lab;
GRANT SELECT ON ws_organization TO lab;
GRANT SELECT ON geo_mountain TO lab;
GRANT SELECT ON geo_desert TO lab;
GRANT SELECT ON geo_island TO lab;
GRANT SELECT ON geo_river TO lab;
GRANT SELECT ON geo_sea TO lab;
GRANT SELECT ON geo_lake TO lab;
GRANT SELECT ON encompasses TO lab;
GRANT SELECT ON is_member TO lab;
GRANT SELECT ON merges_with TO lab;
GRANT SELECT ON located TO lab;
GRANT SELECT ON organization TO lab;
GRANT SELECT ON continent TO lab;
GRANT SELECT ON borders TO lab;
GRANT SELECT ON mountain TO lab;
GRANT SELECT ON desert TO lab;
GRANT SELECT ON island TO lab;
GRANT SELECT ON lake TO lab;
GRANT SELECT ON sea TO lab;
GRANT SELECT ON river TO lab;
GRANT SELECT ON country TO lab;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO lab;

-- End of XMLSQL log