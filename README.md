# LMO Confined Field Ecological Database

A relational database and local web interface for ecological baseline records of the living modified
organism (LMO) confined field of the National Institute of Ecology (NIE), Seocheon-gun, Republic of Korea
(36°01′43.4″ N, 126°43′21.8″ E).

The database keeps each record together with its source file, original row, time precision and review
status, and it defines field and laboratory experiments by factors, levels, replication and measurement
items so that individual measurements can be entered into pre-defined slots.

## Requirements

Python 3.10 or later. Only the standard library is used.

## Run

```
python app.py
```

The interface opens at `http://127.0.0.1:5083` (the next free port is used if 5083 is taken). The server
listens on the local address only. Set `LMO_NO_BROWSER=1` to start without opening a browser,
`LMO_PORT` to choose the port and `LMO_DB_PATH` to use another database file.

## Contents

| Path | Content |
|---|---|
| `app.py` | HTTP server and routes |
| `database.py` | Connection, summary, record detail, survey-date linking, revision history |
| `extensions.py` | Experiment-design and aerial-inventory routes |
| `importer.py` | CSV import with exact-header mapping and duplicate check by content hash |
| `public/` | Web interface (HTML, CSS, JavaScript; no external libraries) |
| `instance/ecology.sqlite` | Bundled database |
| `schema.sql` | Table and view definitions |
| `data/occurrence_darwin_core.csv` | Plant and arthropod records in Darwin Core terms |
| `tests/test_app.py` | Tests of the database, the import routine and the HTTP routes |

## Bundled database

| Data | Rows | Period |
|---|---|---|
| Plant occurrence records | 116 (58 taxa) | 2019–2022 |
| Arthropod presence/absence records | 472 (234 taxa) | 2020–2021 |
| Daily weather, Seocheon AWS 614 and Gunsan ASOS 140 | 5,690 | 2019-01-01 to 2026-10-15 |
| Aerial imagery inventory | 96 months | 2019–2026 |
| Experiment designs | 21 experiments, 37 unit sets, 155 measurement items | 2019–2025 |
| Measurement slots | 12,808 (no values entered) | – |

Plant and arthropod records were published as data sets with Han et al. (2023, GEO DATA 5, 213–221,
https://doi.org/10.22761/GD.2023.0022) and Kim et al. (2025, GEO DATA 7, 377–385,
https://doi.org/10.22761/GD.2025.0018). Weather values were retrieved from the Korea Meteorological
Administration API Hub; request URLs without credentials are kept in `weather_api_source`.

## Interface

| Menu | Function |
|---|---|
| Database overview | Record counts by group, year and time precision; weather availability |
| Observations | Filter by taxon, group, year and source; open a record with its source row; export the selection |
| Review | Open and reviewed quality issues |
| Weather | Daily series and monthly summaries by station |
| Experiment designs | Factors, levels, replication, items and slots of each experiment; shared measurement labels |
| Aerial imagery inventory | Monthly production coverage |
| Facilities and plots | Register facilities and plots |
| Import data | Import a CSV file |
| Database schema | Tables, columns and foreign keys; download as SVG |
| Revision history | The 100 most recent changes with previous and new values |

Changes made through the interface (survey-date links, taxon reviews, issue reviews, registrations,
imports) are written to `revision_history`.

## Standard CSV for import

```
group_name,taxon_label,scientific_name,korean_name,survey_year,survey_month,survey_date,measurement_type,value,unit,raw_value
```

`group_name` is `plants` or `arthropods`; `measurement_type` is `presence_label` or `individual_count`
(unit `count`). Leave unverified months and days blank.

## Tests

```
python -m unittest discover -s tests
```

## Licence

Code: MIT License (see `LICENSE`). Database contents: Creative Commons Attribution 4.0 International.
