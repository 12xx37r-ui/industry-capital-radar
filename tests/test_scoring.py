import unittest

from src.scoring import score_industry


CFG = {
    "capital_flow": {"capital_level":0.2,"capital_velocity":0.3,"capital_acceleration":0.5},
    "demand_validation": {"orders_velocity":0.4,"backlog_acceleration":0.3,"capacity_tightness":0.3},
    "innovation_talent": {"hiring_velocity":0.6,"innovation_velocity":0.4},
    "structural_support": {"official_activity":0.55,"macro_fit":0.45},
    "evidence_strength": {"breadth":0.55,"persistence":0.45},
    "supply_chain_confirmation": {"supply_chain_spillover":1.0},
    "market_heat": {"market_attention":0.25,"price_momentum":0.35,"valuation_heat":0.4},
    "risk_penalty": {"supply_overbuild_risk":0.65,"policy_dependency_risk":0.35},
    "boom_transition": {
        "capital_flow_score":0.25,"demand_validation_score":0.2,"innovation_talent_score":0.1,
        "structural_support_score":0.15,"evidence_strength_score":0.15,
        "supply_chain_confirmation_score":0.15
    },
    "lead_opportunity": {
        "boom_transition_score":0.45,"underrecognition_score":0.2,
        "valuation_attractiveness":0.2,"macro_fit":0.15,"risk_penalty_subtract":0.25
    }
}


class ScoringTests(unittest.TestCase):
    def test_low_attention_strong_fundamentals_rank_well(self):
        row = {
            "capital_level":70,"capital_velocity":80,"capital_acceleration":90,
            "orders_velocity":75,"backlog_acceleration":80,"capacity_tightness":70,
            "hiring_velocity":65,"innovation_velocity":75,"official_activity":72,
            "breadth":75,"persistence":70,"macro_fit":65,"supply_chain_spillover":74,
            "market_attention":20,"price_momentum":25,"valuation_heat":30,
            "valuation_attractiveness":70,
            "supply_overbuild_risk":20,"policy_dependency_risk":25,
            "source_coverage":90,"freshness_score":85,"source_reliability":90,
        }
        out = score_industry(row, CFG)
        self.assertGreater(out["lead_opportunity_score"], 60)
        self.assertFalse(out["is_probability"])

    def test_overheated_market_reduces_opportunity(self):
        base = {
            "capital_level":80,"capital_velocity":80,"capital_acceleration":80,
            "orders_velocity":80,"backlog_acceleration":80,"capacity_tightness":80,
            "hiring_velocity":80,"innovation_velocity":80,"official_activity":80,
            "breadth":80,"persistence":80,"macro_fit":80,"supply_chain_spillover":80,
            "valuation_attractiveness":60,
            "supply_overbuild_risk":35,"policy_dependency_risk":20,
            "source_coverage":90,"freshness_score":90,"source_reliability":90,
        }
        cool = score_industry({**base,"market_attention":20,"price_momentum":20,"valuation_heat":20}, CFG)
        hot = score_industry({**base,"market_attention":95,"price_momentum":95,"valuation_heat":95}, CFG)
        self.assertGreater(cool["lead_opportunity_score"], hot["lead_opportunity_score"])

    def test_missing_features_are_not_zero(self):
        row = {
            "capital_velocity":80,"capital_acceleration":70,"orders_velocity":65,
            "breadth":75,"persistence":70,"market_attention":30,"price_momentum":35,
            "source_coverage":45,"freshness_score":90,"source_reliability":90,
        }
        out = score_industry(row, CFG)
        self.assertIsNotNone(out["boom_transition_12m_score"])
        self.assertGreater(out["capital_flow_score"], 70)
        self.assertIsNone(out["innovation_talent_score"])


if __name__ == "__main__":
    unittest.main()
