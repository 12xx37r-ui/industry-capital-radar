from __future__ import annotations

from typing import Mapping

from .quality import clamp, quality_label, quality_score


def _weighted(row: Mapping[str, float], weights: Mapping[str, float]) -> float:
    total = sum(float(v) for v in weights.values())
    if total <= 0:
        raise ValueError("weight total must be positive")
    return clamp(sum(clamp(row.get(k, 0.0)) * float(w) for k, w in weights.items()) / total)


def classify_stage(boom_transition: float, market_heat: float, risk_penalty: float) -> str:
    if market_heat >= 85 and risk_penalty >= 60:
        return "OVERHEAT_OR_OVERBUILD"
    if boom_transition < 35:
        return "RESEARCH_OBSERVATION"
    if boom_transition < 50:
        return "LATENT_ACCUMULATION"
    if boom_transition < 65:
        return "CAPITAL_VALIDATION"
    if boom_transition < 80:
        return "EARLY_EXPANSION"
    if market_heat < 70:
        return "BOOM_FORMATION"
    return "PUBLIC_BOOM"


def score_industry(row: dict[str, float], cfg: dict) -> dict:
    capital_flow = _weighted(row, cfg["capital_flow"])
    demand_validation = _weighted(row, cfg["demand_validation"])
    innovation_talent = _weighted(row, cfg["innovation_talent"])
    structural_support = _weighted(row, cfg["structural_support"])
    evidence_strength = _weighted(row, cfg["evidence_strength"])
    market_heat = _weighted(row, cfg["market_heat"])
    risk_penalty = _weighted(row, cfg["risk_penalty"])

    derived = dict(row)
    derived.update({
        "capital_flow_score": capital_flow,
        "demand_validation_score": demand_validation,
        "innovation_talent_score": innovation_talent,
        "structural_support_score": structural_support,
        "evidence_strength_score": evidence_strength,
    })
    boom_transition = _weighted(derived, cfg["boom_transition"])
    underrecognition = clamp(100.0 - market_heat)

    lead_cfg = cfg["lead_opportunity"]
    lead_opportunity = clamp(
        boom_transition * lead_cfg["boom_transition_score"]
        + underrecognition * lead_cfg["underrecognition_score"]
        + clamp(row.get("macro_fit", 0.0)) * lead_cfg["macro_fit"]
        - risk_penalty * lead_cfg["risk_penalty_subtract"]
    )

    q_score = quality_score(row)
    return {
        "capital_flow_score": round(capital_flow, 2),
        "demand_validation_score": round(demand_validation, 2),
        "innovation_talent_score": round(innovation_talent, 2),
        "structural_support_score": round(structural_support, 2),
        "evidence_strength_score": round(evidence_strength, 2),
        "market_heat_score": round(market_heat, 2),
        "underrecognition_score": round(underrecognition, 2),
        "risk_penalty_score": round(risk_penalty, 2),
        "capital_inflow_6m_score": round(0.65 * capital_flow + 0.35 * evidence_strength, 2),
        "boom_transition_12m_score": round(boom_transition, 2),
        "core_industry_shift_24m_score": round(0.60 * boom_transition + 0.40 * structural_support, 2),
        "lead_opportunity_score": round(lead_opportunity, 2),
        "stage": classify_stage(boom_transition, market_heat, risk_penalty),
        "confidence_score": q_score,
        "data_quality": quality_label(q_score),
        "is_probability": False
    }
