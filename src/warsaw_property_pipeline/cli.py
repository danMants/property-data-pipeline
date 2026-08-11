from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from .config import load_sources, select_sources
from .extract import DaneGovClient, read_csv_rows
from .load import connect, initialize_schema, load_records
from .models import ApartmentPriceRecord, SourceConfig
from .normalize import normalize_rows


DEFAULT_CONFIG = "config/sources.json"
DEFAULT_RAW_DIR = "data/raw"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="warsaw-property-pipeline",
        description="Collect and normalize Warsaw apartment prices from dane.gov.pl",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Create PostgreSQL tables and views")
    init_db.add_argument("--database-url")

    for command, help_text in (
        ("preview", "Fetch, normalize, and print records without using PostgreSQL"),
        ("ingest", "Fetch, normalize, and load records into PostgreSQL"),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument("--config", default=DEFAULT_CONFIG)
        subparser.add_argument("--source", action="append", dest="sources")
        subparser.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
        if command == "preview":
            subparser.add_argument("--limit", type=int, default=3)
        else:
            subparser.add_argument("--database-url")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init-db":
            database_url = _database_url(args.database_url)
            with connect(database_url) as connection:
                initialize_schema(connection)
            print("PostgreSQL schema is ready")
            return

        sources = select_sources(load_sources(args.config), args.sources)
        client = DaneGovClient()
        if args.command == "preview":
            _preview(client, sources, Path(args.raw_dir), args.limit)
        elif args.command == "ingest":
            _ingest(
                client,
                sources,
                Path(args.raw_dir),
                _database_url(args.database_url),
            )
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc


def _preview(
    client: DaneGovClient,
    sources: list[SourceConfig],
    raw_dir: Path,
    limit: int,
) -> None:
    if limit < 1:
        raise ValueError("--limit must be at least 1")
    for source in sources:
        records, stats = _run_source(client, source, raw_dir)
        print(_summary(source, records, stats))
        for record in records[:limit]:
            printable = asdict(record)
            printable.pop("raw_payload")
            print(json.dumps(printable, ensure_ascii=False, default=str))


def _ingest(
    client: DaneGovClient,
    sources: list[SourceConfig],
    raw_dir: Path,
    database_url: str,
) -> None:
    with connect(database_url) as connection:
        for source in sources:
            records, stats = _run_source(client, source, raw_dir)
            loaded = load_records(connection, records)
            print(f"{_summary(source, records, stats)}; loaded={loaded}")


def _run_source(
    client: DaneGovClient,
    source: SourceConfig,
    raw_dir: Path,
) -> tuple[list[ApartmentPriceRecord], dict[str, int]]:
    resource, content = client.latest_csv(source)
    source_dir = raw_dir / source.name
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_path = source_dir / f"{resource.observed_on}-{resource.resource_id}.csv"
    raw_path.write_bytes(content)
    rows = read_csv_rows(content)
    records, stats = normalize_rows(rows, source, resource)
    stats["resource_id"] = int(resource.resource_id)
    return records, stats


def _summary(
    source: SourceConfig,
    records: list[ApartmentPriceRecord],
    stats: dict[str, int],
) -> str:
    observed_on = records[0].observed_on if records else "n/a"
    return (
        f"{source.name}: observed_on={observed_on}; resource={stats['resource_id']}; "
        f"rows={stats['input_rows']}; normalized={stats['normalized']}; "
        f"non_residential={stats['non_residential']}; invalid={stats['invalid']}; "
        f"older_price_rows={stats['older_prices']}"
    )


def _database_url(argument: str | None) -> str:
    value = argument or os.environ.get("DATABASE_URL")
    if not value:
        raise ValueError("Set DATABASE_URL or pass --database-url")
    return value

