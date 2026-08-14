import unittest

from warsaw_property_pipeline.extract import read_csv_rows


class ReadCsvRowsTests(unittest.TestCase):
    def test_reads_semicolon_delimited_utf8_with_bom(self) -> None:
        content = '\ufeff"Nazwa dewelopera";Powierzchnia\n"Deweloper Ł";52,40\n'.encode(
            "utf-8"
        )

        rows = read_csv_rows(content)

        self.assertEqual(rows[0]["Nazwa dewelopera"], "Deweloper Ł")
        self.assertEqual(rows[0]["Powierzchnia"], "52,40")


if __name__ == "__main__":
    unittest.main()

