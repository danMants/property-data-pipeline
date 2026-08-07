from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, Iterable

from .models import ApartmentPriceRecord


def connect(database_url: str) -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL support is not installed. Run: pip install -e ."
        ) from exc
    return psycopg.connect(database_url)


def initialize_schema(connection: Any) -> None:
    schema = files("warsaw_property_pipeline").joinpath("schema.sql").read_text()
    with connection.cursor() as cursor:
        cursor.execute(schema)
    connection.commit()


def load_records(connection: Any, records: Iterable[ApartmentPriceRecord]) -> int:
    loaded = 0
    with connection.transaction(), connection.cursor() as cursor:
        for record in records:
            cursor.execute(
                """
                INSERT INTO developers (name)
                VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (record.developer,),
            )
            developer_id = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO investments (developer_id, name, city, district, street)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (developer_id, name) DO UPDATE SET
                    city = EXCLUDED.city,
                    district = COALESCE(EXCLUDED.district, investments.district),
                    street = COALESCE(EXCLUDED.street, investments.street)
                RETURNING id
                """,
                (
                    developer_id,
                    record.investment,
                    record.city,
                    record.district,
                    record.street,
                ),
            )
            investment_id = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO apartments (
                    investment_id, source_apartment_id, property_type, area_m2,
                    rooms, floor, available
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (investment_id, source_apartment_id) DO UPDATE SET
                    property_type = EXCLUDED.property_type,
                    area_m2 = EXCLUDED.area_m2,
                    rooms = COALESCE(EXCLUDED.rooms, apartments.rooms),
                    floor = COALESCE(EXCLUDED.floor, apartments.floor),
                    available = EXCLUDED.available,
                    updated_at = now()
                RETURNING id
                """,
                (
                    investment_id,
                    record.source_apartment_id,
                    record.property_type,
                    record.area_m2,
                    record.rooms,
                    record.floor,
                    record.available,
                ),
            )
            apartment_id = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO price_snapshots (
                    apartment_id, observed_on, price_valid_from, area_m2,
                    price_pln, price_per_m2, currency, source_name,
                    source_resource_id, raw_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (apartment_id, observed_on) DO UPDATE SET
                    price_valid_from = EXCLUDED.price_valid_from,
                    area_m2 = EXCLUDED.area_m2,
                    price_pln = EXCLUDED.price_pln,
                    price_per_m2 = EXCLUDED.price_per_m2,
                    source_resource_id = EXCLUDED.source_resource_id,
                    raw_payload = EXCLUDED.raw_payload,
                    ingested_at = now()
                """,
                (
                    apartment_id,
                    record.observed_on,
                    record.price_valid_from,
                    record.area_m2,
                    record.price_pln,
                    record.price_per_m2,
                    record.currency,
                    record.source_name,
                    record.resource_id,
                    json.dumps(record.raw_payload, ensure_ascii=False),
                ),
            )
            loaded += 1
    return loaded

