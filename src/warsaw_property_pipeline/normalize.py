from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .models import ApartmentPriceRecord, ResourceSnapshot, SourceConfig


class NormalizationError(ValueError):
    pass


_MISSING = {"", "x", "n/a", "na", "null", "none", "brak", "-"}
_RESIDENTIAL_MARKERS = (
    "lokalmieszkalny",
    "mieszkanie",
    "apartament",
    "domjednorodzinny",
)


def normalize_rows(
    rows: list[dict[str, str]],
    source: SourceConfig,
    resource: ResourceSnapshot,
) -> tuple[list[ApartmentPriceRecord], dict[str, int]]:
    current_by_apartment: dict[str, ApartmentPriceRecord] = {}
    stats = {"input_rows": len(rows), "non_residential": 0, "invalid": 0, "older_prices": 0}

    for row in rows:
        try:
            record = normalize_row(row, source, resource)
        except NormalizationError:
            stats["invalid"] += 1
            continue
        if record is None:
            stats["non_residential"] += 1
            continue

        previous = current_by_apartment.get(record.source_apartment_id)
        if previous is None or record.price_valid_from >= previous.price_valid_from:
            if previous is not None:
                stats["older_prices"] += 1
            current_by_apartment[record.source_apartment_id] = record
        else:
            stats["older_prices"] += 1

    records = sorted(
        current_by_apartment.values(), key=lambda record: record.source_apartment_id
    )
    stats["normalized"] = len(records)
    return records, stats


def normalize_row(
    row: dict[str, str],
    source: SourceConfig,
    resource: ResourceSnapshot,
) -> ApartmentPriceRecord | None:
    fields = _FieldReader(row, source.column_map)
    property_type = fields.get(
        "property_type", starts=("rodzajnieruchomosci",)
    )
    if not property_type:
        return None
    if not any(marker in canonical(property_type) for marker in _RESIDENTIAL_MARKERS):
        return None

    developer = source.developer or fields.get(
        "developer", exact=("nazwadewelopera",)
    )
    investment = fields.get("investment", exact=("nazwainwestycji",)) or source.investment
    apartment_id = fields.get(
        "apartment_id",
        exact=(
            "nrnieruchomoscinadanyprzezdewelopera",
            "nrlokalulubdomujednorodzinnegonadanyprzezdewelopera",
            "idnieruchomosci",
        ),
    )
    if not developer or not investment or not apartment_id:
        raise NormalizationError("missing apartment identity")

    price = parse_decimal(
        fields.get(
            "price_pln",
            exact=("cenanieruchomosci",),
            starts=(
                "cenalokalumieszkalnegolubdomujednorodzinnegobedacychprzedmiotemumowystanowiacailoczyn",
                "cenalokalumieszkalnegolubdomujednorodzinnegouwzgledniajacacene",
            ),
        )
    )
    price_per_m2 = parse_decimal(
        fields.get(
            "price_per_m2",
            exact=("cenazam2nieruchomosci",),
            starts=("cenam2powierzchniuzytkowej",),
        )
    )
    area = parse_decimal(fields.get("area_m2", exact=("powierzchnia",)))

    if area is None and price is not None and price_per_m2 not in (None, Decimal(0)):
        area = (price / price_per_m2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if price is None and area is not None and price_per_m2 is not None:
        price = (area * price_per_m2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if price_per_m2 is None and price is not None and area not in (None, Decimal(0)):
        price_per_m2 = (price / area).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    if area is None or area <= 0 or price is None or price <= 0 or price_per_m2 is None:
        raise NormalizationError("missing or invalid price/area")

    valid_from = parse_date(
        fields.get(
            "price_valid_from",
            exact=("dataodktorejobowiazujecenanieruchomosci",),
            starts=(
                "dataodktorejcenaobowiazujecenam2powierzchniuzytkowej",
                "dataodktorejcenaobowiazujecenalokalumieszkalnego",
                "dataodktorejobowiazujecenalokalumieszkalnego",
            ),
        )
    ) or resource.observed_on

    currency = fields.get("currency", exact=("waluta",)) or "PLN"
    if canonical(currency) != "pln":
        raise NormalizationError(f"unsupported currency: {currency}")

    city = fields.get(
        "city",
        starts=("miejscowosclokalizacjiprzedsięwzięcia", "miejscowosclokalizacjiprzedsiewziecia"),
    ) or "Warszawa"
    street = fields.get(
        "street",
        starts=("ulicalokalizacjiprzedsiewziecia",),
    )
    rooms = parse_int(fields.get("rooms", exact=("liczbapokoi",)), minimum=0)
    floor = clean_value(fields.get("floor", exact=("pietronieruchomosci",)))

    return ApartmentPriceRecord(
        source_name=source.name,
        resource_id=resource.resource_id,
        developer=developer.strip(),
        investment=investment.strip(),
        source_apartment_id=apartment_id.strip(),
        property_type=property_type.strip(),
        city=city.strip(),
        district=source.district,
        street=street.strip() if street else None,
        area_m2=area.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        rooms=rooms,
        floor=floor,
        currency="PLN",
        price_pln=price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        price_per_m2=price_per_m2.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
        price_valid_from=valid_from,
        observed_on=resource.observed_on,
        available=True,
        raw_payload=row,
    )


class _FieldReader:
    def __init__(self, row: dict[str, str], column_map: dict[str, str]) -> None:
        self.row = row
        self.column_map = column_map
        self.by_canonical = {canonical(key): value for key, value in row.items()}

    def get(
        self,
        field_name: str,
        *,
        exact: tuple[str, ...] = (),
        starts: tuple[str, ...] = (),
    ) -> str | None:
        override = self.column_map.get(field_name)
        if override:
            return clean_value(self.row.get(override))
        for candidate in exact:
            value = clean_value(self.by_canonical.get(canonical(candidate)))
            if value is not None:
                return value
        canonical_starts = tuple(canonical(candidate) for candidate in starts)
        for key, raw_value in self.by_canonical.items():
            if canonical_starts and key.startswith(canonical_starts):
                value = clean_value(raw_value)
                if value is not None:
                    return value
        return None


def canonical(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.replace("²", "2"))
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", without_marks.lower())


def clean_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip('"').strip()
    return None if canonical(text) in _MISSING else text


def parse_decimal(value: object) -> Decimal | None:
    text = clean_value(value)
    if text is None:
        return None
    compact = re.sub(r"[^0-9,.-]", "", text.replace("\u00a0", ""))
    if not compact:
        return None
    if "," in compact and "." in compact:
        if compact.rfind(",") > compact.rfind("."):
            compact = compact.replace(".", "").replace(",", ".")
        else:
            compact = compact.replace(",", "")
    elif "," in compact:
        compact = compact.replace(",", ".")
    try:
        return Decimal(compact)
    except InvalidOperation:
        return None


def parse_int(value: object, minimum: int | None = None) -> int | None:
    number = parse_decimal(value)
    if number is None or number != number.to_integral_value():
        return None
    result = int(number)
    return None if minimum is not None and result < minimum else result


def parse_date(value: object) -> date | None:
    text = clean_value(value)
    if text is None:
        return None
    candidate = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate).date()
    except ValueError:
        try:
            return date.fromisoformat(candidate[:10])
        except ValueError:
            return None
