from __future__ import annotations

import math
from typing import Any

from .quality import clamp


def _score_growth(value: float | None, scale: float = 1.5) -> float | None:
    if value is None:
        return None
    return clamp(50 + 50 * math.tanh(scale * value))


def _blend(values: list[tuple[float | None, float]]) -> float | None:
    pairs = [(float(v), float(w)) for v, w in values if isinstance(v, (int, float))]
    total = sum(w for _, w in pairs)
    return None if total <= 0 else clamp(sum(v * w for v, w in pairs) / total)


def rank_companies(industry_score: float | None, companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for company in companies:
        operational = _blend([
            (_score_growth(company.get("capex_growth"), 1.0), 0.25),
            (_score_growth(company.get("revenue_growth"), 2.0), 0.20),
            (_score_growth(company.get("operating_income_growth"), 1.5), 0.20),
            (_score_growth(company.get("employee_growth"), 2.0), 0.15),
            (_score_growth(company.get("orders_growth"), 1.0), 0.20),
        ])
        return_score = _score_growth(company.get("return_6m"), 2.0)
        underrecognition = None if return_score is None else 100.0 - return_score
        valuation = company.get("valuation_attractiveness")
        final = _blend([
            (industry_score, 0.40),
            (operational, 0.30),
            (underrecognition, 0.15),
            (valuation, 0.15),
        ])
        results.append({
            "name": company.get("name"),
            "stock_code": company.get("stock_code"),
            "beneficiary_candidate_score": round(final, 2) if final is not None else None,
            "operational_signal_score": round(operational, 2) if operational is not None else None,
            "underrecognition_score": round(underrecognition, 2) if underrecognition is not None else None,
            "valuation_attractiveness_score": valuation,
            "pe": company.get("pe"),
            "pb": company.get("pb"),
            "latest_price": company.get("latest_price"),
            "market_cap": company.get("market_cap"),
            "capex_growth": company.get("capex_growth"),
            "revenue_growth": company.get("revenue_growth"),
            "employee_growth": company.get("employee_growth"),
            "orders_growth": company.get("orders_growth"),
            "return_6m": company.get("return_6m"),
            "valuation_is_approximate": True,
        })
    results.sort(key=lambda x: (x["beneficiary_candidate_score"] is not None, x["beneficiary_candidate_score"] or -1), reverse=True)
    return results


def build_top10(radar_rows: list[dict[str, Any]], details: dict[str, Any]) -> list[dict[str, Any]]:
    top: list[dict[str, Any]] = []
    for rank, industry in enumerate(radar_rows[:10], start=1):
        industry_id = industry["industry_id"]
        evidence = (details.get(industry_id) or {}).get("evidence") or {}
        companies = rank_companies(industry.get("lead_opportunity_score"), evidence.get("companies") or [])
        top.append({
            "rank": rank,
            "industry_id": industry_id,
            "industry_name_ko": industry.get("industry_name_ko"),
            "stage": industry.get("stage"),
            "lead_opportunity_score": industry.get("lead_opportunity_score"),
            "boom_transition_12m_score": industry.get("boom_transition_12m_score"),
            "core_industry_shift_24m_score": industry.get("core_industry_shift_24m_score"),
            "underrecognition_score": industry.get("underrecognition_score"),
            "valuation_attractiveness_score": industry.get("valuation_attractiveness_score"),
            "beneficiary_companies": companies[:5],
        })
    return top
