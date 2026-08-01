import unittest

from src.collectors.ecos import _aggregate_duplicate_periods, discover_item, discover_table, series_signal


class EcosTests(unittest.TestCase):
    def test_discovery_and_signal(self):
        tables = [
            {"STAT_CODE": "A", "STAT_NAME": "소비자물가", "CYCLE": "M", "SRCH_YN": "Y"},
            {"STAT_CODE": "B", "STAT_NAME": "광공업생산지수", "CYCLE": "M", "SRCH_YN": "Y"},
        ]
        table = discover_table(tables, ["산업생산지수", "광공업생산지수"])
        self.assertEqual(table["STAT_CODE"], "B")
        items = [
            {"ITEM_CODE": "1", "ITEM_NAME": "광공업 총지수", "CYCLE": "M", "END_TIME": "202606"},
            {"ITEM_CODE": "2", "ITEM_NAME": "기타", "CYCLE": "M", "END_TIME": "202606"},
        ]
        item = discover_item(items, ["광공업", "총지수"])
        self.assertEqual(item["ITEM_CODE"], "1")
        rows = [{"time": f"2025{i:02d}", "value": 100 + i} for i in range(1, 13)]
        metric = series_signal(rows)
        self.assertGreater(metric["score"], 50)

    def test_duplicate_periods_are_aggregated_before_growth(self):
        raw = [
            {"TIME": "202501", "DATA_VALUE": "10", "ITEM_NAME2": "서울"},
            {"TIME": "202501", "DATA_VALUE": "20", "ITEM_NAME2": "부산"},
            {"TIME": "202502", "DATA_VALUE": "11", "ITEM_NAME2": "서울"},
            {"TIME": "202502", "DATA_VALUE": "21", "ITEM_NAME2": "부산"},
        ]
        rows, duplicates = _aggregate_duplicate_periods(raw)
        self.assertEqual(duplicates, 2)
        self.assertEqual(rows[0]["value"], 30)
        self.assertEqual(rows[1]["value"], 32)


if __name__ == "__main__":
    unittest.main()
