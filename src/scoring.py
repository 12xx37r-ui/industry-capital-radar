from __future__ import annotations

from typing import Any, Mapping

from .quality import clamp, quality_label, quality_score


def _valid(value: Any) -> bool:
    return isinstance(value, (int, float))


def _weighted(row: Mapping[str, Any], weights: Mapping[str, float]) -> float | None:
    pairs = [(float(row[k]), float(w)) for k, w in weights.items() if _valid(row.get(k))]
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    return clamp(sum(clamp(v) * w for v, w in pairs) / total)


def _blend_available(values: list[tuple[float | None, float]]) -> float | None:
    pairs = [(float(v), float(w)) for v, w in values if _valid(v)]
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    return clamp(sum(v * w for v, w in pairs) / total)


def classify_stage(boom_transition: float | None, market_heat: float | None, risk_penalty: float | None) -> str:
    if boom_transition is None:
        return "INSUFFICIENT_DATA"
    market_heat = 50.0 if market_heat is None else market_heat
    risk_penalty = 0.0 if risk_penalty is None else risk_penalty
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


def _round(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def score_industry(row: dict[str, Any], cfg: dict) -> dict[str, Any]:
    capital_flow = _weighted(row, cfg["capital_flow"])
    demand_validation = _weighted(row, cfg["demand_validation"])
    innovation_talent = _weighted(row, cfg["innovation_talent"])
    structural_support = _weighted(row, cfg["structural_support"])
    evidence_strength = _weighted(row, cfg["evidence_strength"])
    market_heat = _weighted(row, cfg["market_heat"])
    risk_penalty = _weighted(row, cfg["risk_penalty"])

    derived: dict[str, Any] = dict(row)
    derived.update({
        "capital_flow_score": capital_flow,
        "demand_validation_score": demand_validation,
        "innovation_talent_score": innovation_talent,
        "structural_support_score": structural_support,
        "evidence_strength_score": evidence_strength,
    })
    boom_transition = _weighted(derived, cfg["boom_transition"])
    underrecognition = clamp(100.0 - market_heat) if market_heat is not None else None

    lead_cfg = cfg["lead_opportunity"]
    positive = _blend_available([
        (boom_transition, lead_cfg["boom_transition_score"]),
        (underrecognition, lead_cfg["underrecognition_score"]),
        (row.get("macro_fit"), lead_cfg["macro_fit"]),
    ])
    lead_opportunity = None
    if positive is not None:
        lead_opportunity = positive
        if risk_penalty is not None:
            lead_opportunity = clamp(lead_opportunity - risk_penalty * lead_cfg["risk_penalty_subtract"])

    q_score = quality_score(row)
    return {
        "capital_flow_score": _round(capital_flow),
        "demand_validation_score": _round(demand_validation),
        "innovation_talent_score": _round(innovation_talent),
        "structural_support_score": _round(structural_support),
        "evidence_strength_score": _round(evidence_strength),
        "market_heat_score": _round(market_heat),
        "underrecognition_score": _round(underrecognition),
        "risk_penalty_score": _round(risk_penalty),
        "macro_fit_score": _round(row.get("macro_fit") if _valid(row.get("macro_fit")) else None),
        "capital_inflow_6m_score": _round(_blend_available([(capital_flow, 0.65), (evidence_strength, 0.35)])),
        "boom_transition_12m_score": _round(boom_transition),
        "core_industry_shift_24m_score": _round(_blend_available([(boom_transition, 0.60), (structural_support, 0.40)])),
        "lead_opportunity_score": _round(lead_opportunity),
        "stage": classify_stage(boom_transition, market_heat, risk_penalty),
        "confidence_score": q_score,
        "data_quality": quality_label(q_score),
        "is_probability": False,
    }
