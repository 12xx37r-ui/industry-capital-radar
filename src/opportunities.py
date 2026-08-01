from __future__ import annotations

import math
from typing import Any

from .quality import clamp


def _score_growth(value: float | None, scale: float = 1.5) -> float | None:
    if value is None:
        return None
    return clamp(50 + 50 * math.tanh(scale * max(-3.0, min(3.0, value))))


def _blend(values: list[tuple[float | None, float]]) -> float | None:
    pairs = [(float(v), float(w)) for v, w in values if isinstance(v, (int, float)) and float(w) > 0]
    total = sum(w for _, w in pairs)
    return None if total <= 0 else clamp(sum(v * w for v, w in pairs) / total)


def _company_penalties(
    company: dict[str, Any],
    operational: float | None,
    realization: float | None,
    valuation: float | None,
    return_score: float | None,
) -> tuple[float, float, float]:
    prepricing = 0.0
    if return_score is not None:
        prepricing += max(0.0, return_score - 68.0) * 1.8
    pb = company.get("pb")
    if isinstance(pb, (int, float)) and pb > 5.0:
        prepricing += min(35.0, (pb - 5.0) * 7.0)
    prepricing = clamp(prepricing)

    value_trap = 0.0
    if valuation is not None:
        confirmation = _blend([(operational, 0.45), (realization, 0.55)])
        if confirmation is None:
            confirmation = 35.0
        value_trap = clamp(
            100.0
            * max(0.0, valuation - 55.0) / 45.0
            * max(0.0, 52.0 - confirmation) / 52.0
        )

    capex = company.get("capex_growth")
    revenue = company.get("revenue_growth")
    employees = company.get("employee_growth")
    orders = company.get("orders_growth")
    overbuild = 0.0
    if isinstance(capex, (int, float)) and capex > 0.30:
        negatives = [x for x in (revenue, employees, orders) if isinstance(x, (int, float))]
        if negatives:
            negative_share = sum(1 for x in negatives if x < 0) / len(negatives)
            overbuild = clamp(100.0 * min(1.0, capex / 2.0) * negative_share)
    return round(prepricing, 2), round(value_trap, 2), round(overbuild, 2)


def _signal_state(
    final: float | None,
    operational: float | None,
    realization: float | None,
    prepricing: float,
    value_trap: float,
    overbuild: float,
) -> str:
    if value_trap >= 45:
        return "VALUE_TRAP_RISK"
    if overbuild >= 50:
        return "OVERBUILD_RISK"
    if prepricing >= 55:
        return "PREPRICED"
    if (final or 0.0) >= 72 and (operational or 0.0) >= 58 and (realization or 0.0) >= 50:
        return "EARLY_BENEFICIARY"
    if (final or 0.0) >= 60:
        return "VALIDATING"
    return "SPECULATIVE"


def rank_companies(industry_score: float | None, companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for company in companies:
        capex_expansion = _blend([
            (_score_growth(company.get("capex_growth"), 0.9), 0.60),
            (_score_growth(company.get("capex_acceleration"), 1.3), 0.40),
        ])
        realization = _blend([
            (_score_growth(company.get("revenue_growth"), 2.0), 0.30),
            (_score_growth(company.get("operating_income_growth"), 1.5), 0.25),
            (_score_growth(company.get("employee_growth"), 2.0), 0.15),
            (_score_growth(company.get("orders_growth"), 1.0), 0.30),
        ])
        operational = _blend([
            (capex_expansion, 0.45),
            (realization, 0.55),
        ])
        return_score = _score_growth(company.get("return_6m"), 2.0)
        underrecognition = None if return_score is None else 100.0 - return_score
        valuation = company.get("valuation_attractiveness")
        valuation_confidence = company.get("valuation_data_confidence")
        if isinstance(valuation, (int, float)) and isinstance(valuation_confidence, (int, float)):
            effective_valuation = 50.0 + (float(valuation) - 50.0) * clamp(float(valuation_confidence)) / 100.0
        else:
            effective_valuation = valuation if isinstance(valuation, (int, float)) else None

        prepricing, value_trap, overbuild = _company_penalties(
            company, operational, realization, effective_valuation, return_score
        )
        final = _blend([
            (industry_score, 0.35),
            (operational, 0.30),
            (realization, 0.10),
            (underrecognition, 0.15),
            (effective_valuation, 0.10),
        ])
        if final is not None:
            final = clamp(final - prepricing * 0.18 - value_trap * 0.15 - overbuild * 0.12)
        state = _signal_state(final, operational, realization, prepricing, value_trap, overbuild)
        results.append({
            "name": company.get("name"),
            "stock_code": company.get("stock_code"),
            "beneficiary_candidate_score": round(final, 2) if final is not None else None,
            "signal_state": state,
            "operational_signal_score": round(operational, 2) if operational is not None else None,
            "capex_expansion_score": round(capex_expansion, 2) if capex_expansion is not None else None,
            "realization_confirmation_score": round(realization, 2) if realization is not None else None,
            "underrecognition_score": round(underrecognition, 2) if underrecognition is not None else None,
            "valuation_attractiveness_score": round(effective_valuation, 2) if effective_valuation is not None else None,
            "valuation_data_confidence_score": valuation_confidence,
            "market_prepricing_penalty_score": prepricing,
            "value_trap_risk_score": value_trap,
            "overbuild_risk_score": overbuild,
            "pe": company.get("pe"),
            "pb": company.get("pb"),
            "latest_price": company.get("latest_price"),
            "market_cap": company.get("market_cap"),
            "capex_growth": company.get("capex_growth"),
            "capex_acceleration": company.get("capex_acceleration"),
            "revenue_growth": company.get("revenue_growth"),
            "operating_income_growth": company.get("operating_income_growth"),
            "employee_growth": company.get("employee_growth"),
            "orders_growth": company.get("orders_growth"),
            "return_6m": company.get("return_6m"),
            "valuation_is_approximate": True,
        })
    results.sort(
        key=lambda x: (x["beneficiary_candidate_score"] is not None, x["beneficiary_candidate_score"] or -1),
        reverse=True,
    )
    return results


def build_top10(radar_rows: list[dict[str, Any]], details: dict[str, Any]) -> list[dict[str, Any]]:
    top: list[dict[str, Any]] = []
    for rank, industry in enumerate(radar_rows[:10], start=1):
        industry_id = industry["industry_id"]
        evidence = (details.get(industry_id) or {}).get("evidence") or {}
        companies = rank_companies(industry.get("pre_boom_pattern_score"), evidence.get("companies") or [])
        top.append({
            "rank": rank,
            "industry_id": industry_id,
            "industry_name_ko": industry.get("industry_name_ko"),
            "stage": industry.get("stage"),
            "candidate_tier": industry.get("candidate_tier"),
            "next_ai_candidate": industry.get("next_ai_candidate"),
            "pre_boom_pattern_score": industry.get("pre_boom_pattern_score"),
            "lead_opportunity_score": industry.get("lead_opportunity_score"),
            "capital_acceleration_score": industry.get("capital_acceleration_score"),
            "attention_gap_score": industry.get("attention_gap_score"),
            "real_economy_confirmation_score": industry.get("real_economy_confirmation_score"),
            "boom_transition_12m_score": industry.get("boom_transition_12m_score"),
            "core_industry_shift_24m_score": industry.get("core_industry_shift_24m_score"),
            "underrecognition_score": industry.get("underrecognition_score"),
            "market_prepricing_penalty_score": industry.get("market_prepricing_penalty_score"),
            "value_trap_risk_score": industry.get("value_trap_risk_score"),
            "valuation_attractiveness_score": industry.get("valuation_attractiveness_score"),
            "beneficiary_companies": companies[:5],
        })
    return top
