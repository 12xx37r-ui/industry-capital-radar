from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from .quality import clamp


def safe_growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return current / abs(previous) - 1.0


def median(values: Iterable[float | None]) -> float | None:
    valid = [float(x) for x in values if x is not None and math.isfinite(float(x))]
    return statistics.median(valid) if valid else None


def growth_score(value: float | None, scale: float = 1.5) -> float | None:
    if value is None:
        return None
    return round(clamp(50 + 50 * math.tanh(scale * value)), 2)


def ratio_score(value: float | None, midpoint: float = 0.06, width: float = 0.08) -> float | None:
    if value is None:
        return None
    return round(clamp(50 + 50 * math.tanh((value - midpoint) / max(width, 1e-6))), 2)


def breadth_score(flags: list[bool]) -> float | None:
    return round(100 * sum(flags) / len(flags), 2) if flags else None


def risk_score(value: float | None, scale: float = 2.0) -> float | None:
    if value is None:
        return None
    return round(clamp(100 * math.tanh(scale * max(0.0, value))), 2)


def valuation_attractiveness(pe: float | None, pb: float | None) -> float | None:
    scores: list[tuple[float, float]] = []
    if pe is not None and pe > 0:
        pe_score = 100.0 - max(0.0, pe - 12.0) * 2.8 - max(0.0, 5.0 - pe) * 5.0
        scores.append((clamp(pe_score), 0.60))
    if pb is not None and pb > 0:
        pb_score = 100.0 - max(0.0, pb - 1.5) * 18.0 - max(0.0, 0.45 - pb) * 35.0
        scores.append((clamp(pb_score), 0.40))
    if not scores:
        return None
    total = sum(w for _, w in scores)
    return round(sum(v * w for v, w in scores) / total, 2)


def _company_period_metrics(company: dict[str, Any]) -> dict[str, Any]:
    years = sorted((int(y) for y in (company.get("annual") or {}).keys()), reverse=True)
    if len(years) < 2:
        return {}
    y0, y1 = years[0], years[1]
    y2 = years[2] if len(years) > 2 else None
    a0 = company["annual"].get(str(y0), {})
    a1 = company["annual"].get(str(y1), {})
    a2 = company["annual"].get(str(y2), {}) if y2 else {}
    market = company.get("market") or {}
    shares = company.get("shares") or {}
    latest_price = market.get("latest_price")
    issued_shares = shares.get("issued_shares") or shares.get("floating_shares")
    market_cap = latest_price * issued_shares if latest_price is not None and issued_shares not in (None, 0) else None
    net_income = a0.get("net_income")
    equity = a0.get("equity")
    pe = market_cap / net_income if market_cap is not None and net_income not in (None, 0) and net_income > 0 else None
    pb = market_cap / equity if market_cap is not None and equity not in (None, 0) and equity > 0 else None

    out = {
        "latest_year": y0,
        "capex_ratio": (a0.get("capex") / abs(a0.get("revenue"))) if a0.get("capex") is not None and a0.get("revenue") not in (None, 0) else None,
        "capex_growth": safe_growth(a0.get("capex"), a1.get("capex")),
        "capex_prev_growth": safe_growth(a1.get("capex"), a2.get("capex")) if y2 else None,
        "revenue_growth": safe_growth(a0.get("revenue"), a1.get("revenue")),
        "operating_income_growth": safe_growth(a0.get("operating_income"), a1.get("operating_income")),
        "inventory_growth": safe_growth(a0.get("inventory"), a1.get("inventory")),
        "ppe_growth": safe_growth(a0.get("ppe"), a1.get("ppe")),
        "employee_growth": safe_growth(a0.get("employees"), a1.get("employees")),
        "return_6m": market.get("return_6m"),
        "return_12m": market.get("return_12m"),
        "volume_acceleration": market.get("volume_acceleration"),
        "latest_price": latest_price,
        "market_cap": market_cap,
        "pe": pe,
        "pb": pb,
        "valuation_attractiveness": valuation_attractiveness(pe, pb),
    }
    out["capex_acceleration"] = (
        out["capex_growth"] - out["capex_prev_growth"]
        if out["capex_growth"] is not None and out["capex_prev_growth"] is not None else None
    )
    disc = company.get("disclosures") or {}
    curr, prev = disc.get("orders_curr"), disc.get("orders_prev")
    out["orders_growth"] = ((curr + 1) / (prev + 1) - 1) if curr is not None and prev is not None and (curr > 0 or prev > 0) else None
    return out


def build_industry_features(
    companies: list[dict[str, Any]],
    industry_ids: list[str],
    macro_scores: dict[str, float | None] | None = None,
    official_scores: dict[str, float | None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    macro_scores = macro_scores or {}
    official_scores = official_scores or {}
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for company in companies:
        metrics = _company_period_metrics(company)
        if not metrics:
            continue
        for industry_id in company.get("industries", []):
            grouped[industry_id].append((company, metrics))

    benchmark_return = median((c.get("market") or {}).get("return_6m") for c in companies)
    rows: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {}
    now = datetime.now(timezone.utc).date().isoformat()
    feature_keys = [
        "capital_level", "capital_velocity", "capital_acceleration", "orders_velocity",
        "backlog_acceleration", "capacity_tightness", "hiring_velocity", "innovation_velocity",
        "official_activity", "breadth", "persistence", "macro_fit", "supply_chain_spillover",
        "market_attention", "price_momentum", "valuation_heat", "valuation_attractiveness",
        "supply_overbuild_risk", "policy_dependency_risk",
    ]

    for industry_id in industry_ids:
        items = grouped.get(industry_id, [])
        if len(items) < 2:
            continue
        metrics = [m for _, m in items]
        capex_ratio = median(m.get("capex_ratio") for m in metrics)
        capex_growth = median(m.get("capex_growth") for m in metrics)
        capex_acc = median(m.get("capex_acceleration") for m in metrics)
        orders_growth = median(m.get("orders_growth") for m in metrics)
        rev_growth = median(m.get("revenue_growth") for m in metrics)
        op_growth = median(m.get("operating_income_growth") for m in metrics)
        inv_growth = median(m.get("inventory_growth") for m in metrics)
        employee_growth = median(m.get("employee_growth") for m in metrics)
        return_6m = median(m.get("return_6m") for m in metrics)
        vol_acc = median(m.get("volume_acceleration") for m in metrics)
        valuation_score = median(m.get("valuation_attractiveness") for m in metrics)
        capacity = (rev_growth - inv_growth) if rev_growth is not None and inv_growth is not None else op_growth

        available_company_signals: list[bool] = []
        persistence_flags: list[bool] = []
        for m in metrics:
            checks = [x for x in (m.get("capex_growth"), m.get("revenue_growth"), m.get("employee_growth"), m.get("orders_growth")) if x is not None]
            if checks:
                available_company_signals.append(sum(1 for x in checks if x > 0) >= max(1, len(checks) // 2 + 1))
            if m.get("capex_growth") is not None and m.get("capex_prev_growth") is not None:
                persistence_flags.append(m["capex_growth"] > 0 and m["capex_prev_growth"] > 0)

        overbuild_components = []
        if capex_growth is not None and rev_growth is not None:
            overbuild_components.append(max(0.0, capex_growth - rev_growth))
        if inv_growth is not None and rev_growth is not None:
            overbuild_components.append(max(0.0, inv_growth - rev_growth))
        overbuild_raw = median(overbuild_components)

        row: dict[str, Any] = {
            "industry_id": industry_id,
            "as_of_date": now,
            "capital_level": ratio_score(capex_ratio),
            "capital_velocity": growth_score(capex_growth),
            "capital_acceleration": growth_score(capex_acc, 2.0),
            "orders_velocity": growth_score(orders_growth, 1.0),
            "backlog_acceleration": None,
            "capacity_tightness": growth_score(capacity, 1.5),
            "hiring_velocity": growth_score(employee_growth, 2.0),
            "innovation_velocity": None,
            "official_activity": official_scores.get(industry_id),
            "breadth": breadth_score(available_company_signals),
            "persistence": breadth_score(persistence_flags),
            "macro_fit": macro_scores.get(industry_id),
            "supply_chain_spillover": None,
            "market_attention": growth_score(vol_acc, 1.0),
            "price_momentum": growth_score((return_6m - benchmark_return) if return_6m is not None and benchmark_return is not None else None, 2.0),
            "valuation_heat": None if valuation_score is None else round(100.0 - valuation_score, 2),
            "valuation_attractiveness": valuation_score,
            "supply_overbuild_risk": risk_score(overbuild_raw, 2.0),
            "policy_dependency_risk": None,
        }
        populated = sum(row.get(k) is not None for k in feature_keys)
        row["source_coverage"] = round(100 * populated / len(feature_keys), 2)
        latest_year = max((m.get("latest_year", 0) for m in metrics), default=0)
        current_year = datetime.now(timezone.utc).year
        row["freshness_score"] = 92.0 if latest_year >= current_year - 1 else 72.0 if latest_year >= current_year - 2 else 42.0
        official_connected = row.get("official_activity") is not None
        row["source_reliability"] = 94.0 if official_connected else 86.0
        rows.append(row)

        ranked = sorted(items, key=lambda cm: (cm[1].get("capex_growth") is not None, cm[1].get("capex_growth") or -999), reverse=True)
        evidence[industry_id] = {
            "sample_company_count": len(items),
            "companies": [
                {
                    "name": c.get("name"), "stock_code": c.get("stock_code"),
                    "capex_growth": m.get("capex_growth"), "revenue_growth": m.get("revenue_growth"),
                    "operating_income_growth": m.get("operating_income_growth"),
                    "employee_growth": m.get("employee_growth"), "return_6m": m.get("return_6m"),
                    "latest_price": m.get("latest_price"), "market_cap": m.get("market_cap"),
                    "pe": m.get("pe"), "pb": m.get("pb"),
                    "valuation_attractiveness": m.get("valuation_attractiveness"),
                    "orders_growth": m.get("orders_growth"),
                    "orders_curr": (c.get("disclosures") or {}).get("orders_curr"),
                    "orders_prev": (c.get("disclosures") or {}).get("orders_prev"),
                }
                for c, m in ranked
            ],
            "official_activity_score": official_scores.get(industry_id),
            "macro_fit_score": macro_scores.get(industry_id),
            "limitations": [
                "대표기업 표본 기반이며 산업 전체 모집단이 아닙니다.",
                "OpenDART·KOSIS·ECOS·FRED와 보조 시장가격 신호를 결합합니다.",
                "특허·정부예산·조달 원문은 후속 버전에서 별도 연결합니다.",
                "기업 저평가는 DART 연차 순이익·자본과 최근 주가로 계산한 근사 P/E·P/B입니다."
            ],
        }
    return rows, evidence
