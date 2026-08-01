import unittest

from src.supply_chain import compute_spillovers


class SupplyChainTests(unittest.TestCase):
    def test_spillover_uses_direct_and_second_hop_sources(self):
        scores = {
            "A": {"capital_acceleration_score": 90, "demand_validation_score": 80, "boom_transition_12m_score": 80, "underrecognition_score": 70},
            "B": {"capital_acceleration_score": 70, "demand_validation_score": 60, "boom_transition_12m_score": 60, "underrecognition_score": 60},
            "C": {"boom_transition_12m_score": 40},
            "D": {"boom_transition_12m_score": 30},
        }
        graph = {
            "second_hop_decay": 0.45,
            "edges": [
                {"from": "A", "to": "C", "weight": 0.75, "relation": "x"},
                {"from": "B", "to": "C", "weight": 0.25, "relation": "y"},
                {"from": "C", "to": "D", "weight": 0.80, "relation": "z"},
            ],
        }
        spillovers, breadth, evidence = compute_spillovers(scores, graph)
        self.assertIsNotNone(spillovers["C"])
        self.assertGreater(spillovers["C"], 60)
        self.assertIsNotNone(breadth["C"])
        self.assertTrue(any(link["hop"] == 2 for link in evidence["D"]))


if __name__ == "__main__":
    unittest.main()
