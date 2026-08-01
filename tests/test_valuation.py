import unittest

from src.normalize import valuation_attractiveness, valuation_data_confidence


class ValuationTests(unittest.TestCase):
    def test_reasonable_multiples_score_higher(self):
        reasonable = valuation_attractiveness(10, 1.2)
        expensive = valuation_attractiveness(45, 7.0)
        self.assertIsNotNone(reasonable)
        self.assertIsNotNone(expensive)
        self.assertGreater(reasonable, expensive)

    def test_pb_only_does_not_automatically_score_100(self):
        score = valuation_attractiveness(None, 0.35)
        self.assertIsNotNone(score)
        self.assertLessEqual(score, 82)
        self.assertEqual(valuation_data_confidence(None, 0.35), 60)

    def test_missing_multiples_returns_none(self):
        self.assertIsNone(valuation_attractiveness(None, None))


if __name__ == "__main__":
    unittest.main()
