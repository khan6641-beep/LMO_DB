CREATE VIEW aerial_inventory AS SELECT m.year,COUNT(*) managed_months,SUM(m.reported_monthly_products) reported_products,SUM(m.status='planned') planned_months,(SELECT COUNT(*) FROM aerial_asset a WHERE a.year=m.year) linked_files FROM aerial_month m GROUP BY m.year;

CREATE VIEW experiment_inventory AS
      SELECT e.id experiment_id, s.name unit_set,
        (SELECT COUNT(*) FROM experimental_unit u WHERE u.unit_set_id=s.id) units,
        (SELECT COUNT(*) FROM measurement_item m WHERE m.unit_set_id=s.id) items,
        (SELECT COUNT(*) FROM experiment_value v JOIN experimental_unit u ON u.id=v.unit_id WHERE u.unit_set_id=s.id) value_slots,
        (SELECT COUNT(*) FROM experiment_value v JOIN experimental_unit u ON u.id=v.unit_id
           WHERE u.unit_set_id=s.id AND v.status='measured') measured_values
      FROM experiment e JOIN experiment_unit_set s ON s.experiment_id=e.id;

CREATE VIEW weather_monthly AS
SELECT station_id,CAST(substr(date,1,4) AS INTEGER) AS year,CAST(substr(date,6,2) AS INTEGER) AS month,
 count(*) AS calendar_days,
 avg(temperature_mean_c) AS temperature_observed_daily_mean_c,
 count(temperature_mean_c) AS temperature_valid_days,
 min(temperature_min_c) AS temperature_min_c,
 max(temperature_max_c) AS temperature_max_c,
 sum(precipitation_mm) AS precipitation_observed_sum_mm,
 count(precipitation_mm) AS precipitation_valid_days,
 CASE WHEN count(precipitation_mm)=count(*) THEN sum(precipitation_mm) END AS precipitation_complete_total_mm,
 avg(humidity_mean_pct) AS humidity_observed_daily_mean_pct,
 count(humidity_mean_pct) AS humidity_valid_days
FROM weather_daily GROUP BY station_id,substr(date,1,4),substr(date,6,2);

CREATE VIEW weather_yearly AS
SELECT station_id,CAST(substr(date,1,4) AS INTEGER) AS year,count(*) AS calendar_days,
 avg(temperature_mean_c) AS temperature_observed_daily_mean_c,
 count(temperature_mean_c) AS temperature_valid_days,
 min(temperature_min_c) AS temperature_min_c,
 max(temperature_max_c) AS temperature_max_c,
 sum(precipitation_mm) AS precipitation_observed_sum_mm,
 count(precipitation_mm) AS precipitation_valid_days,
 CASE WHEN count(precipitation_mm)=count(*) THEN sum(precipitation_mm) END AS precipitation_complete_total_mm,
 avg(humidity_mean_pct) AS humidity_observed_daily_mean_pct,
 count(humidity_mean_pct) AS humidity_valid_days
FROM weather_daily GROUP BY station_id,substr(date,1,4);

CREATE TABLE aerial_asset(id INTEGER PRIMARY KEY,year INTEGER NOT NULL,month INTEGER NOT NULL,path TEXT NOT NULL,sha256 TEXT NOT NULL UNIQUE,product_type TEXT NOT NULL,acquisition_date TEXT,FOREIGN KEY(year,month) REFERENCES aerial_month(year,month));

CREATE TABLE aerial_month(year INTEGER NOT NULL,month INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),status TEXT NOT NULL CHECK(status IN ('reported_production','planned')),reported_monthly_products INTEGER NOT NULL CHECK(reported_monthly_products>=0),evidence_note TEXT NOT NULL,PRIMARY KEY(year,month));

CREATE TABLE experiment(id TEXT PRIMARY KEY, title TEXT NOT NULL, start TEXT NOT NULL, setting TEXT NOT NULL);

CREATE TABLE experiment_factor_level(unit_set_id INTEGER NOT NULL REFERENCES experiment_unit_set(id),
      factor TEXT NOT NULL, level_order INTEGER NOT NULL, level TEXT NOT NULL,
      PRIMARY KEY(unit_set_id, factor, level_order));

CREATE TABLE experiment_unit_set(id INTEGER PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiment(id),
      name TEXT NOT NULL, unit_label TEXT NOT NULL, replicate_label TEXT NOT NULL, replicate_n INTEGER,
      status TEXT NOT NULL CHECK(status IN ('enumerated','replicates_unresolved')), note TEXT,
      UNIQUE(experiment_id, name));

CREATE TABLE experiment_value(unit_id INTEGER NOT NULL REFERENCES experimental_unit(id),
      item_id INTEGER NOT NULL REFERENCES measurement_item(id), value REAL, value_text TEXT,
      status TEXT NOT NULL DEFAULT 'awaiting_raw_data' CHECK(status IN ('awaiting_raw_data','measured')),
      PRIMARY KEY(unit_id, item_id));

CREATE TABLE experimental_unit(id INTEGER PRIMARY KEY, unit_set_id INTEGER NOT NULL REFERENCES experiment_unit_set(id),
      levels_json TEXT NOT NULL, replicate INTEGER NOT NULL, UNIQUE(unit_set_id, levels_json, replicate));

CREATE TABLE facility(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,description TEXT);

CREATE TABLE import_file(source_id INTEGER PRIMARY KEY REFERENCES source_file(id),stored_name TEXT,format TEXT NOT NULL,created_at TEXT NOT NULL);

CREATE TABLE measurement_definition(code TEXT PRIMARY KEY,name_en TEXT NOT NULL,canonical_unit TEXT NOT NULL,domain TEXT NOT NULL);

CREATE TABLE measurement_item(id INTEGER PRIMARY KEY, unit_set_id INTEGER NOT NULL REFERENCES experiment_unit_set(id),
      label TEXT NOT NULL, UNIQUE(unit_set_id, label));

CREATE TABLE observation(id INTEGER PRIMARY KEY,source_id INTEGER REFERENCES source_file(id),row_number INTEGER,source_column INTEGER,taxon_id INTEGER REFERENCES taxon(id),survey_year INTEGER,survey_month INTEGER,survey_date TEXT,time_precision TEXT,measurement_type TEXT,value REAL,unit TEXT,raw_value TEXT,plot_id INTEGER,coordinate_status TEXT,UNIQUE(source_id,row_number,source_column));

CREATE TABLE observation_context(observation_id INTEGER PRIMARY KEY REFERENCES observation(id),event_id INTEGER NOT NULL REFERENCES survey_event(id),sample_id INTEGER REFERENCES sample(id));

CREATE TABLE observation_weather(observation_id INTEGER REFERENCES observation(id),station_id TEXT,date TEXT,match_status TEXT,FOREIGN KEY(station_id,date) REFERENCES weather_daily(station_id,date));

CREATE TABLE plot(id INTEGER PRIMARY KEY,facility_id INTEGER NOT NULL REFERENCES facility(id),code TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('control','experimental','unspecified')),notes TEXT,UNIQUE(facility_id,code));

CREATE TABLE quality_issue(id INTEGER PRIMARY KEY,source_id INTEGER REFERENCES source_file(id),source_column INTEGER,observation_id INTEGER REFERENCES observation(id),code TEXT NOT NULL,description TEXT NOT NULL,affected_count INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','reviewed')),note TEXT,reviewed_at TEXT);

CREATE TABLE raw_row(source_id INTEGER REFERENCES source_file(id),row_number INTEGER,cells_json TEXT NOT NULL,PRIMARY KEY(source_id,row_number));

CREATE TABLE revision_history(id INTEGER PRIMARY KEY,entity_type TEXT NOT NULL,entity_id INTEGER NOT NULL,field_name TEXT NOT NULL,old_json TEXT,new_json TEXT,reason TEXT NOT NULL,changed_at TEXT NOT NULL);

CREATE TABLE sample(id INTEGER PRIMARY KEY,event_id INTEGER NOT NULL REFERENCES survey_event(id),code TEXT NOT NULL,notes TEXT,UNIQUE(event_id,code));

CREATE TABLE source_file(id INTEGER PRIMARY KEY,name TEXT NOT NULL,sha256 TEXT NOT NULL,encoding TEXT NOT NULL);

CREATE TABLE survey_event(id INTEGER PRIMARY KEY,facility_id INTEGER REFERENCES facility(id),plot_id INTEGER REFERENCES plot(id),survey_date TEXT NOT NULL,method TEXT,notes TEXT);

CREATE TABLE taxon(id INTEGER PRIMARY KEY,group_name TEXT,label TEXT,scientific_name TEXT,korean_name TEXT,rank_status TEXT,UNIQUE(group_name,label));

CREATE TABLE unresolved_cell(source_id INTEGER REFERENCES source_file(id),row_number INTEGER,column_number INTEGER,raw_value TEXT,reason TEXT,PRIMARY KEY(source_id,row_number,column_number));

CREATE TABLE weather_api_source (url TEXT PRIMARY KEY, response_sha256 TEXT NOT NULL, raw_cache_path TEXT NOT NULL, record_count INTEGER NOT NULL, retrieved_at TEXT NOT NULL);

CREATE TABLE weather_daily(station_id TEXT REFERENCES weather_station(station_id),date TEXT,temperature_mean_c REAL,temperature_min_c REAL,temperature_max_c REAL,precipitation_mm REAL,humidity_mean_pct REAL,humidity_min_pct REAL,humidity_max_pct REAL,wind_mean_ms REAL,wind_max_ms REAL,pressure_mean_hpa REAL,source_url TEXT,qc_json TEXT,PRIMARY KEY(station_id,date));

CREATE TABLE weather_station(station_id TEXT PRIMARY KEY,name TEXT,provider TEXT,latitude REAL,longitude REAL);

CREATE INDEX obs_source_column ON observation(source_id,source_column);

CREATE INDEX obs_taxon ON observation(taxon_id);

CREATE INDEX obs_time_context ON observation(time_precision,survey_year,survey_month);

CREATE INDEX observation_time_context ON observation(time_precision,survey_year,survey_month);

CREATE INDEX quality_status ON quality_issue(status,code);

CREATE INDEX revision_entity ON revision_history(entity_type,entity_id);