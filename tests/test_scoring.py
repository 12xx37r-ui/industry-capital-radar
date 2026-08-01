import json
import unittest
from pathlib import Path

from src.scoring import score_industry


CFG = json.loads((Path(__file__).resolve().parents[1] / "config" / "model_weights.json").read_text(encoding="utf-8"))


class ScoringTests(unittest.TestCase):
    def test_low_attention_strong_fundamentals_rank_well(self):
        row = {
            "capital_level": 70, "capital_velocity": 80, "capital_acceleration": 90,
            "orders_velocity": 75, "backlog_acceleration": 80, "capacity_tightness": 70,
            "hiring_velocity": 65, "innovation_velocity": 75, "official_activity": 72,
            "breadth": 75, "persistence": 70, "macro_fit": 65,
            "supply_chain_spillover": 74, "supply_chain_breadth": 65,
            "market_attention": 20, "price_momentum": 25, "valuation_heat": 30,
            "valuation_attractiveness": 70, "valuation_data_confidence": 90,
            "supply_overbuild_risk": 20, "policy_dependency_risk": 25,
            "source_coverage": 90, "freshness_score": 85, "source_reliability": 90,
        }
        out = score_industry(row, CFG)
        self.assertGreater(out["pre_boom_pattern_score"], 60)
        self.assertIn(out["candidate_tier"], {"A", "B", "C"})
        self.assertFalse(out["is_probability"])

    def test_overheated_market_reduces_opportunity(self):
        base = {
            "capital_level": 80, "capital_velocity": 80, "capital_acceleration": 80,
            "orders_velocity": 80, "backlog_acceleration": 80, "capacity_tightness": 80,
            "hiring_velocity": 80, "innovation_velocity": 80, "official_activity": 80,
            "breadth": 80, "persistence": 80, "macro_fit": 80,
            "supply_chain_spillover": 80, "supply_chain_breadth": 75,
            "valuation_attractiveness": 60, "valuation_data_confidence": 100,
            "supply_overbuild_risk": 35, "policy_dependency_risk": 20,
            "source_coverage": 90, "freshness_score": 90, "source_reliability": 90,
        }
        cool = score_industry({**base, "market_attention": 20, "price_momentum": 20, "valuation_heat": 20}, CFG)
        hot = score_industry({**base, "market_attention": 95, "price_momentum": 95, "valuation_heat": 95}, CFG)
        self.assertGreater(cool["pre_boom_pattern_score"], hot["pre_boom_pattern_score"])
        self.assertGreater(cool["lead_opportunity_score"], hot["lead_opportunity_score"])

    def test_cheap_without_confirmation_gets_value_trap_penalty(self):
        row = {
            "capital_level": 40, "capital_velocity": 35, "capital_acceleration": 30,
            "orders_velocity": 25, "capacity_tightness": 25,
            "hiring_velocity": 30, "official_activity": 45,
            "breadth": 25, "persistence": 20, "macro_fit": 50,
            "supply_chain_spillover": 35, "supply_chain_breadth": 20,
            "market_attention": 20, "price_momentum": 20, "valuation_heat": 10,
            "valuation_attractiveness": 90, "valuation_data_confidence": 60,
            "source_coverage": 75, "freshness_score": 90, "source_reliability": 90,
        }
        out = score_industry(row, CFG)
        self.assertGreater(out["value_trap_risk_score"], 0)
        self.assertLess(out["pre_boom_pattern_score"], 50)

    def test_missing_features_are_not_zero(self):
        row = {
            "capital_velocity": 80, "capital_acceleration": 70, "orders_velocity": 65,
            "breadth": 75, "persistence": 70, "market_attention": 30, "price_momentum": 35,
            "source_coverage": 45, "freshness_score": 90, "source_reliability": 90,
        }
        out = score_industry(row, CFG)
        self.assertIsNotNone(out["boom_transition_12m_score"])
        self.assertGreater(out["capital_flow_score"], 70)
        self.assertIsNone(out["innovation_talent_score"])


if __name__ == "__main__":
    unittest.main()
