import unittest

from src.collectors.fred import compute_regime, map_industry_scores


class FredTests(unittest.TestCase):
    def test_regime_and_mapping(self):
        def rows(values):
            return [{"date": f"2025-{i+1:02d}-01", "value": v} for i, v in enumerate(values)]

        series = {
            "DGS2": rows([5.0] * 70 + [4.8, 4.6, 4.4]),
            "T10Y2Y": rows([-0.5, -0.2, 0.1]),
            "CPIAUCSL": rows([100 + i * 0.2 for i in range(20)]),
            "CPILFESL": rows([100 + i * 0.18 for i in range(20)]),
            "UNRATE": rows([4.2, 4.1, 4.0, 3.9]),
            "PAYEMS": rows([100 + i for i in range(12)]),
            "INDPRO": rows([100 + i * 0.3 for i in range(12)]),
            "DGORDER": rows([100 + i * 0.4 for i in range(12)]),
            "WALCL": rows([100 + i * 0.1 for i in range(20)]),
        }
        regime = compute_regime(series)
        self.assertIsNotNone(regime["overall_score"])
        cfg = {
            "default": "balanced",
            "profiles": {"balanced": {"growth": 0.4, "rates": 0.3, "liquidity": 0.1, "inflation": 0.2}},
            "industry_profiles": {},
        }
        mapped = map_industry_scores(regime, cfg, ["ROBOTICS"])
        self.assertIsNotNone(mapped["ROBOTICS"])


if __name__ == "__main__":
    unittest.main()
