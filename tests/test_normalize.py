import unittest
from datetime import date
from decimal import Decimal

from warsaw_property_pipeline.models import ResourceSnapshot, SourceConfig
from warsaw_property_pipeline.normalize import normalize_row, normalize_rows


SOURCE = SourceConfig(
    name="example",
    dataset_id=1,
    investment="Fallback Investment",
    district="Wola",
)
RESOURCE = ResourceSnapshot(
    resource_id="123",
    title="Example",
    observed_on=date(2026, 8, 17),
    download_url="https://example.test/data.csv",
)


class NormalizeTests(unittest.TestCase):
    def test_normalizes_standard_dane_gov_columns(self) -> None:
        row = {
            "Nazwa dewelopera": "Example Developer",
            "Nazwa inwestycji": "Example Estate",
            "Rodzaj nieruchomości: lokal mieszkalny, dom jednorodzinny": "Lokal mieszkalny",
            "Nr nieruchomości nadany przez dewelopera": "A-42",
            "Powierzchnia": "52,40",
            "Liczba pokoi": "3",
            "Piętro nieruchomości": "4",
            "Waluta": "PLN",
            "Cena za m2 nieruchomości": "17156,49",
            "Cena nieruchomości": "899000,00",
            "Data od której obowiązuje cena nieruchomości": "2026-08-01 10:30:00",
            "Miejscowość lokalizacji przedsięwzięcia deweloperskiego lub zadania inwestycyjnego": "Warszawa",
            "Ulica lokalizacji przedsięwzięcia deweloperskiego lub zadania inwestycyjnego": "Prosta",
        }

        record = normalize_row(row, SOURCE, RESOURCE)

        self.assertIsNotNone(record)
        self.assertEqual(record.source_apartment_id, "A-42")
        self.assertEqual(record.area_m2, Decimal("52.40"))
        self.assertEqual(record.price_pln, Decimal("899000.00"))
        self.assertEqual(record.rooms, 3)
        self.assertEqual(record.price_valid_from, date(2026, 8, 1))

    def test_derives_area_for_long_form_noho_schema(self) -> None:
        row = {
            "Nazwa dewelopera": "NOHO Warszawa sp. z o.o.",
            "Rodzaj nieruchomości: lokal mieszkalny, dom jednorodzinny ": "Apartament",
            "Nr lokalu lub domu jednorodzinnego nadany przez dewelopera": "A/A2.04.54",
            "Cena m 2 powierzchni użytkowej lokalu mieszkalnego / domu jednorodzinnego [zł]": "49453.82",
            "Cena lokalu mieszkalnego lub domu jednorodzinnego będących przedmiotem umowy stanowiąca iloczyn ceny m2 oraz powierzchni [zł]": "4980000",
            "Data od której cena obowiązuje cena lokalu mieszkalnego lub domu jednorodzinnego będących przedmiotem umowy stanowiąca iloczyn ceny m2 oraz powierzchni": "2025-09-03 15:21:04",
            "Miejscowość lokalizacji przedsięwzięcia deweloperskiego lub zadania inwestycyjnego": "Warszawa",
        }

        record = normalize_row(row, SOURCE, RESOURCE)

        self.assertIsNotNone(record)
        self.assertEqual(record.area_m2, Decimal("100.70"))
        self.assertEqual(record.price_per_m2, Decimal("49453.82"))
        self.assertEqual(record.price_valid_from, date(2025, 9, 3))

    def test_rejects_parking_places(self) -> None:
        row = {
            "Rodzaj nieruchomości: lokal mieszkalny, dom jednorodzinny": "Miejsce postojowe",
        }

        self.assertIsNone(normalize_row(row, SOURCE, RESOURCE))

    def test_ignores_rows_without_a_property_type(self) -> None:
        row = {
            "Nazwa dewelopera": "Example Developer",
            "Rodzaj nieruchomości: lokal mieszkalny, dom jednorodzinny": "X",
        }

        self.assertIsNone(normalize_row(row, SOURCE, RESOURCE))

    def test_keeps_latest_price_per_apartment_in_one_resource(self) -> None:
        base = {
            "Nazwa dewelopera": "Example Developer",
            "Nazwa inwestycji": "Example Estate",
            "Rodzaj nieruchomości: lokal mieszkalny, dom jednorodzinny": "Lokal mieszkalny",
            "Nr nieruchomości nadany przez dewelopera": "A-42",
            "Powierzchnia": "50",
            "Waluta": "PLN",
            "Cena za m2 nieruchomości": "18000",
        }
        older = {
            **base,
            "Cena nieruchomości": "900000",
            "Data od której obowiązuje cena nieruchomości": "2026-07-01",
        }
        latest = {
            **base,
            "Cena nieruchomości": "875000",
            "Cena za m2 nieruchomości": "17500",
            "Data od której obowiązuje cena nieruchomości": "2026-08-01",
        }

        records, stats = normalize_rows([older, latest], SOURCE, RESOURCE)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].price_pln, Decimal("875000.00"))
        self.assertEqual(stats["older_prices"], 1)


if __name__ == "__main__":
    unittest.main()
