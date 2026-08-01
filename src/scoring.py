from __future__ import annotations

from typing import Any, Mapping

from .quality import clamp, quality_label, quality_score


def _valid(value: Any) -> bool:
    return isinstance(value, (int, float))


def _weighted(row: Mapping[str, Any], weights: Mapping[str, float]) -> float | None:
    pairs = [(float(row[k]), float(w)) for k, w in weights.items() if _valid(row.get(k)) and float(w) > 0]
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    return clamp(sum(clamp(v) * w for v, w in pairs) / total)


def _blend_available(values: list[tuple[float | None, float]]) -> float | None:
    pairs = [(float(v), float(w)) for v, w in values if _valid(v) and float(w) > 0]
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    return clamp(sum(clamp(v) * w for v, w in pairs) / total)


def _attention_gap(capital_acceleration: float | None, underrecognition: float | None) -> float | None:
    if capital_acceleration is None or underrecognition is None:
        return None
    # Requiring both sides prevents a dead/cheap industry from scoring highly
    # solely because nobody is watching it.
    floor = min(capital_acceleration, underrecognition)
    average = (capital_acceleration + underrecognition) / 2.0
    return clamp(0.65 * floor + 0.35 * average)


def _market_prepricing_penalty(
    market_heat: float | None,
    price_momentum: float | None,
    market_attention: float | None,
) -> float | None:
    parts: list[tuple[float | None, float]] = []
    if market_heat is not None:
        parts.append((clamp(max(0.0, market_heat - 55.0) * 2.2), 0.50))
    if price_momentum is not None:
        parts.append((clamp(max(0.0, price_momentum - 60.0) * 2.5), 0.35))
    if market_attention is not None:
        parts.append((clamp(max(0.0, market_attention - 65.0) * 2.5), 0.15))
    return _blend_available(parts)


def _value_trap_risk(
    valuation: float | None,
    real_confirmation: float | None,
    capital_acceleration: float | None,
) -> float | None:
    if valuation is None:
        return None
    confirmation = _blend_available([(real_confirmation, 0.65), (capital_acceleration, 0.35)])
    if confirmation is None:
        return clamp(max(0.0, valuation - 55.0) * 1.4)
    cheapness = max(0.0, valuation - 55.0) / 45.0
    confirmation_gap = max(0.0, 55.0 - confirmation) / 55.0
    return clamp(100.0 * cheapness * confirmation_gap)


def classify_stage(
    pre_boom: float | None,
    market_heat: float | None,
    risk_penalty: float | None,
) -> str:
    if pre_boom is None:
        return "INSUFFICIENT_DATA"
    heat = 50.0 if market_heat is None else market_heat
    risk = 0.0 if risk_penalty is None else risk_penalty
    if heat >= 85 and risk >= 55:
        return "OVERHEAT_OR_OVERBUILD"
    if heat >= 75 and pre_boom >= 55:
        return "PUBLIC_BOOM_OR_PREPRICED"
    if pre_boom < 35:
        return "RESEARCH_OBSERVATION"
    if pre_boom < 50:
        return "LATENT_ACCUMULATION"
    if pre_boom < 65:
        return "CAPITAL_VALIDATION"
    if pre_boom < 78:
        return "EARLY_EXPANSION"
    return "BOOM_FORMATION"


def candidate_tier(
    pre_boom: float | None,
    underrecognition: float | None,
    capital_acceleration: float | None,
    market_heat: float | None,
    confidence: float,
) -> str:
    if pre_boom is None or confidence < 55:
        return "OBSERVATION"
    heat = 50.0 if market_heat is None else market_heat
    under = 50.0 if underrecognition is None else underrecognition
    accel = 50.0 if capital_acceleration is None else capital_acceleration
    if pre_boom >= 72 and under >= 58 and accel >= 62 and heat < 68:
        return "A"
    if pre_boom >= 62 and under >= 52 and accel >= 55 and heat < 75:
        return "B"
    if pre_boom >= 52:
        return "C"
    return "OBSERVATION"


def _round(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def score_industry(row: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    capital_flow = _weighted(row, cfg["capital_flow"])
    demand_validation = _weighted(row, cfg["demand_validation"])
    innovation_talent = _weighted(row, cfg["innovation_talent"])
    structural_support = _weighted(row, cfg["structural_support"])
    evidence_strength = _weighted(row, cfg["evidence_strength"])
    supply_chain_confirmation = _weighted(row, cfg["supply_chain_confirmation"])
    market_heat = _weighted(row, cfg["market_heat"])
    risk_penalty = _weighted(row, cfg["risk_penalty"])
    official_activity = row.get("official_activity") if _valid(row.get("official_activity")) else None
    valuation = row.get("valuation_attractiveness") if _valid(row.get("valuation_attractiveness")) else None

    derived: dict[str, Any] = dict(row)
    derived.update({
        "capital_flow_score": capital_flow,
        "demand_validation_score": demand_validation,
        "innovation_talent_score": innovation_talent,
        "structural_support_score": structural_support,
        "official_activity_score": official_activity,
        "evidence_strength_score": evidence_strength,
        "supply_chain_confirmation_score": supply_chain_confirmation,
    })

    capital_acceleration = _weighted(derived, cfg["capital_acceleration"])
    derived["capital_acceleration_score"] = capital_acceleration
    real_confirmation = _weighted(derived, cfg["real_economy_confirmation"])
    derived["real_economy_confirmation_score"] = real_confirmation
    boom_transition = _weighted(derived, cfg["boom_transition"])
    underrecognition = clamp(100.0 - market_heat) if market_heat is not None else None
    attention_gap = _attention_gap(capital_acceleration, underrecognition)
    prepricing_penalty = _market_prepricing_penalty(
        market_heat,
        row.get("price_momentum") if _valid(row.get("price_momentum")) else None,
        row.get("market_attention") if _valid(row.get("market_attention")) else None,
    )
    value_trap = _value_trap_risk(valuation, real_confirmation, capital_acceleration)
    q_score = quality_score(row)
    uncertainty = clamp(100.0 - q_score)

    pre_cfg = cfg["pre_boom_pattern"]
    positive_pre_boom = _blend_available([
        (capital_acceleration, pre_cfg["capital_acceleration_score"]),
        (real_confirmation, pre_cfg["real_economy_confirmation_score"]),
        (attention_gap, pre_cfg["attention_gap_score"]),
        (supply_chain_confirmation, pre_cfg["supply_chain_confirmation_score"]),
        (structural_support, pre_cfg["structural_support_score"]),
        (innovation_talent, pre_cfg["innovation_talent_score"]),
    ])
    pre_boom = positive_pre_boom
    if pre_boom is not None:
        if risk_penalty is not None:
            pre_boom -= risk_penalty * float(pre_cfg["risk_penalty_subtract"])
        if prepricing_penalty is not None:
            pre_boom -= prepricing_penalty * float(pre_cfg["market_prepricing_subtract"])
        if value_trap is not None:
            pre_boom -= value_trap * float(pre_cfg["value_trap_subtract"])
        pre_boom -= uncertainty * float(pre_cfg["uncertainty_subtract"])
        pre_boom = clamp(pre_boom)

    capital_inflow_6m = _blend_available([
        (capital_acceleration, 0.55),
        (capital_flow, 0.25),
        (official_activity, 0.20),
    ])
    core_shift_24m = _blend_available([
        (boom_transition, 0.35),
        (structural_support, 0.30),
        (supply_chain_confirmation, 0.20),
        (innovation_talent, 0.15),
    ])

    lead_cfg = cfg["lead_opportunity"]
    lead_opportunity = _blend_available([
        (pre_boom, lead_cfg["pre_boom_pattern_score"]),
        (valuation, lead_cfg["valuation_attractiveness"]),
        (core_shift_24m, lead_cfg["core_industry_shift_24m_score"]),
    ])
    if lead_opportunity is not None:
        if prepricing_penalty is not None:
            lead_opportunity -= prepricing_penalty * float(lead_cfg["market_prepricing_subtract"])
        if value_trap is not None:
            lead_opportunity -= value_trap * float(lead_cfg["value_trap_subtract"])
        lead_opportunity = clamp(lead_opportunity)

    tier = candidate_tier(pre_boom, underrecognition, capital_acceleration, market_heat, q_score)
    next_ai_candidate = tier in {"A", "B"} and (real_confirmation or 0.0) >= 50.0

    return {
        "capital_flow_score": _round(capital_flow),
        "capital_acceleration_score": _round(capital_acceleration),
        "demand_validation_score": _round(demand_validation),
        "real_economy_confirmation_score": _round(real_confirmation),
        "innovation_talent_score": _round(innovation_talent),
        "structural_support_score": _round(structural_support),
        "official_activity_score": _round(official_activity),
        "evidence_strength_score": _round(evidence_strength),
        "supply_chain_spillover_score": _round(row.get("supply_chain_spillover") if _valid(row.get("supply_chain_spillover")) else None),
        "supply_chain_breadth_score": _round(row.get("supply_chain_breadth") if _valid(row.get("supply_chain_breadth")) else None),
        "supply_chain_confirmation_score": _round(supply_chain_confirmation),
        "market_heat_score": _round(market_heat),
        "underrecognition_score": _round(underrecognition),
        "attention_gap_score": _round(attention_gap),
        "market_prepricing_penalty_score": _round(prepricing_penalty),
        "valuation_attractiveness_score": _round(valuation),
        "valuation_data_confidence_score": _round(row.get("valuation_data_confidence") if _valid(row.get("valuation_data_confidence")) else None),
        "value_trap_risk_score": _round(value_trap),
        "risk_penalty_score": _round(risk_penalty),
        "macro_fit_score": _round(row.get("macro_fit") if _valid(row.get("macro_fit")) else None),
        "capital_inflow_6m_score": _round(capital_inflow_6m),
        "boom_transition_12m_score": _round(boom_transition),
        "core_industry_shift_24m_score": _round(core_shift_24m),
        "pre_boom_pattern_score": _round(pre_boom),
        "lead_opportunity_score": _round(lead_opportunity),
        "candidate_tier": tier,
        "next_ai_candidate": next_ai_candidate,
        "stage": classify_stage(pre_boom, market_heat, risk_penalty),
        "confidence_score": q_score,
        "data_quality": quality_label(q_score),
        "is_probability": False,
    }
