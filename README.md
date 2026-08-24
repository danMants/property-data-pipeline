# Warsaw Property Data Pipeline

[![CI](https://github.com/danMants/property-data-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/danMants/property-data-pipeline/actions/workflows/ci.yml)

An ETL pipeline that collects public apartment-price CSV files from Poland's
official [dane.gov.pl](https://dane.gov.pl/) portal, normalizes data published by
different developers, stores daily price snapshots in PostgreSQL, and exposes
SQL views for district statistics and price drops.

The starter configuration follows three real Warsaw datasets:

- Moje Bielany (`dataset_id=14276`)
- Nowa Mangalia (`dataset_id=18353`)
- NOHO Warszawa (`dataset_id=22103`)

The pipeline resolves the newest CSV resource through the public API on every
run, so the configuration does not depend on a dated download URL.

## What the MVP does

```text
dane.gov.pl dataset API
          |
          v
 newest CSV per developer ----> data/raw/<source>/<date>-<resource>.csv
          |
          v
 normalize Polish headers, decimals, dates, and apartment identifiers
          |
          v
 keep the current residential row per apartment; reject parking/storage rows
          |
          v
 PostgreSQL: developers -> investments -> apartments -> price_snapshots
          |
          v
 latest_apartment_prices | apartment_price_changes | district_statistics
```

Raw files are retained locally for replay and debugging, but ignored by Git.
Repeated ingestion of the same developer and observation date is idempotent.

## Quick start

Requirements: Python 3.11+, Docker, and Docker Compose.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .

docker compose up -d
export DATABASE_URL=postgresql://property:property@localhost:5432/warsaw_property

warsaw-property-pipeline init-db
warsaw-property-pipeline preview --limit 2
warsaw-property-pipeline ingest
```

Preview or ingest only one source:

```bash
warsaw-property-pipeline preview --source moje-bielany --limit 5
warsaw-property-pipeline ingest --source noho-warsaw
```

## Example analytics

Average price per square metre by district:

```sql
SELECT *
FROM district_statistics
ORDER BY avg_price_per_m2 DESC;
```

Recorded price drops:

```sql
SELECT
    investment,
    source_apartment_id,
    previous_price_pln,
    current_price_pln,
    price_change_percent,
    observed_on
FROM apartment_price_changes
WHERE price_change_pln < 0
ORDER BY price_change_percent;
```

Price history for one apartment:

```sql
SELECT ps.observed_on, ps.price_pln, ps.price_per_m2
FROM price_snapshots ps
JOIN apartments a ON a.id = ps.apartment_id
WHERE a.source_apartment_id = 'A-42'
ORDER BY ps.observed_on;
```

## Adding a source

Add another dataset to `config/sources.json`:

```json
{
  "name": "another-investment",
  "dataset_id": 12345,
  "investment": "Investment name",
  "district": "Warsaw district"
}
```

If a publisher uses a genuinely different header, add an explicit map. Keys are
canonical field names used by the pipeline:

```json
{
  "column_map": {
    "apartment_id": "Publisher apartment column",
    "area_m2": "Publisher area column",
    "price_pln": "Publisher total price column"
  }
}
```

Supported mapping keys include `developer`, `investment`, `apartment_id`,
`property_type`, `area_m2`, `rooms`, `floor`, `currency`, `price_pln`,
`price_per_m2`, `price_valid_from`, `city`, and `street`.

## Tests

The unit tests require no database or network access:

```bash
PYTHONPATH=src python3.11 -m unittest discover -s tests -v
```

## Continuous integration and delivery

Every push and pull request runs the unit tests on Python 3.11 and 3.12,
validates the source configuration and CLI, and builds the application
container. The `Required quality gate` job summarizes these checks and is the
status check required before a pull request can merge into `main`.

After a merge into `main`, a separate workflow can publish the image and update
the scheduled ETL job in Azure. Cloud deployment remains disabled until the
Azure resources and GitHub OIDC trust are configured. See
[`docs/azure-deployment.md`](docs/azure-deployment.md) for the activation
checklist.

## Next iterations

1. Schedule daily ingestion and record run-level data-quality metrics.
2. Mark apartments unavailable when they disappear from a developer's latest file.
3. Add a small FastAPI read API for apartments, price history, price drops, and
   district statistics.
4. Deploy the collector, PostgreSQL, and API to Azure.

## Data sources

- [DANE.GOV.PL API documentation](https://api.dane.gov.pl/1.4/doc)
- [Moje Bielany dataset](https://dane.gov.pl/pl/dataset/14276)
- [Nowa Mangalia dataset](https://dane.gov.pl/pl/dataset/18353)
- [NOHO Warszawa dataset](https://dane.gov.pl/pl/dataset/22103)
