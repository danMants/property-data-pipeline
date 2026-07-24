from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SourceConfig:
    name: str
    dataset_id: int
    investment: str
    district: str | None = None
    developer: str | None = None
    column_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    resource_id: str
    title: str
    observed_on: date
    download_url: str


@dataclass(frozen=True, slots=True)
class ApartmentPriceRecord:
    source_name: str
    resource_id: str
    developer: str
    investment: str
    source_apartment_id: str
    property_type: str
    city: str
    district: str | None
    street: str | None
    area_m2: Decimal
    rooms: int | None
    floor: str | None
    currency: str
    price_pln: Decimal
    price_per_m2: Decimal
    price_valid_from: date
    observed_on: date
    available: bool
    raw_payload: dict[str, str]

