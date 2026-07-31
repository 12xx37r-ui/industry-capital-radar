import unittest

from src.collectors.kosis import choose_series, group_series, series_signal


class KosisTests(unittest.TestCase):
    def test_group_and_choose_series(self):
        rows = []
        for period, value in [("202501", "100"), ("202502", "102"), ("202503", "105")]:
            rows.append({
                "ITM_ID": "T1", "ITM_NM": "생산지수", "C1": "00", "C1_NM": "제조업",
                "PRD_DE": period, "DT": value, "TBL_NM": "광공업생산지수"
            })
        series = group_series(rows)
        chosen = choose_series(series, ["생산지수", "제조업"])
        self.assertIsNotNone(chosen)
        metric = series_signal(chosen["rows"])
        self.assertIsNotNone(metric["score"])
        self.assertGreater(metric["score"], 50)


if __name__ == "__main__":
    unittest.main()
