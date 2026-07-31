import unittest

from src.supply_chain import compute_spillovers


class SupplyChainTests(unittest.TestCase):
    def test_spillover_uses_weighted_source_scores(self):
        scores = {
            "A": {"boom_transition_12m_score": 80},
            "B": {"boom_transition_12m_score": 60},
            "C": {"boom_transition_12m_score": 40},
        }
        graph = {
            "edges": [
                {"from": "A", "to": "C", "weight": 0.75, "relation": "x"},
                {"from": "B", "to": "C", "weight": 0.25, "relation": "y"},
            ]
        }
        spillovers, evidence = compute_spillovers(scores, graph)
        self.assertAlmostEqual(spillovers["C"], 75.0)
        self.assertEqual(len(evidence["C"]), 2)


if __name__ == "__main__":
    unittest.main()
