"""FRED macro collector and industry macro-fit mapper."""
from __future__ import annotations

import math
import os
import time
from datetime import datetime, timezone
from typing import Any

from src.http_utils import get_json
from src.quality import clamp

BASE = "https://api.stlouisfed.org/fred/series/observations"


class FredApiError(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.getenv("FRED_API_KEY", "").strip())


def _key() -> str:
    value = os.getenv("FRED_API_KEY", "").strip()
    if not value:
        raise FredApiError("FRED_API_KEY is missing")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def observations(series_id: str, limit: int = 420) -> list[dict[str, Any]]:
    payload = get_json(BASE, {
        "api_key": _key(),
        "file_type": "json",
        "series_id": series_id,
        "sort_order": "asc",
        "limit": str(limit),
    }, timeout=30, retries=1)
    if payload.get("error_code"):
        raise FredApiError(f"FRED {series_id}: {payload.get('error_message')}")
    rows: list[dict[str, Any]] = []
    for item in payload.get("observations") or []:
        raw = item.get("value")
        if raw in (None, ".", ""):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        rows.append({"date": str(item.get("date", "")), "value": value})
    return rows


def _pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return current / abs(previous) - 1.0


def _change(rows: list[dict[str, Any]], periods: int) -> float | None:
    if len(rows) <= periods:
        return None
    return rows[-1]["value"] - rows[-1 - periods]["value"]


def _pct_change(rows: list[dict[str, Any]], periods: int) -> float | None:
    if len(rows) <= periods:
        return None
    return _pct(rows[-1]["value"], rows[-1 - periods]["value"])


def _yoy(rows: list[dict[str, Any]], periods: int = 12) -> float | None:
    return _pct_change(rows, periods)


def _tanh_score(value: float | None, scale: float = 1.0, inverse: bool = False) -> float | None:
    if value is None:
        return None
    direction = -1.0 if inverse else 1.0
    return round(clamp(50.0 + 50.0 * math.tanh(direction * scale * value)), 2)


def _mean_available(items: list[tuple[float | None, float]]) -> float | None:
    pairs = [(float(v), float(w)) for v, w in items if v is not None]
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    return round(clamp(sum(v * w for v, w in pairs) / total), 2)


def compute_regime(series: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    dgs2 = series.get("DGS2", [])
    curve = series.get("T10Y2Y", [])
    cpi = series.get("CPIAUCSL", [])
    core = series.get("CPILFESL", [])
    unrate = series.get("UNRATE", [])
    payroll = series.get("PAYEMS", [])
    indpro = series.get("INDPRO", [])
    orders = series.get("DGORDER", [])
    walcl = series.get("WALCL", [])

    rate_3m_change = _change(dgs2, min(63, max(1, len(dgs2) - 1))) if len(dgs2) > 1 else None
    rate_score = _tanh_score(rate_3m_change, scale=1.2, inverse=True)

    curve_latest = curve[-1]["value"] if curve else None
    curve_score = _tanh_score(curve_latest, scale=0.8)

    cpi_yoy = _yoy(cpi)
    cpi_prev_yoy = _pct(cpi[-4]["value"], cpi[-16]["value"]) if len(cpi) >= 16 else None
    core_yoy = _yoy(core)
    inflation_level = None
    if cpi_yoy is not None and core_yoy is not None:
        inflation_level = (cpi_yoy + core_yoy) / 2.0
    elif cpi_yoy is not None:
        inflation_level = cpi_yoy
    elif core_yoy is not None:
        inflation_level = core_yoy
    inflation_gap = None if inflation_level is None else inflation_level - 0.02
    inflation_level_score = _tanh_score(inflation_gap, scale=10.0, inverse=True)
    disinflation = None if cpi_yoy is None or cpi_prev_yoy is None else cpi_prev_yoy - cpi_yoy
    disinflation_score = _tanh_score(disinflation, scale=20.0)
    inflation_score = _mean_available([(inflation_level_score, 0.65), (disinflation_score, 0.35)])

    unrate_change = _change(unrate, 3)
    unemployment_score = _tanh_score(unrate_change, scale=1.5, inverse=True)
    payroll_growth = _pct_change(payroll, 6)
    payroll_score = _tanh_score(payroll_growth, scale=25.0)
    labor_score = _mean_available([(unemployment_score, 0.45), (payroll_score, 0.55)])

    indpro_growth = _pct_change(indpro, 6)
    orders_growth = _pct_change(orders, 6)
    production_score = _tanh_score(indpro_growth, scale=18.0)
    orders_score = _tanh_score(orders_growth, scale=8.0)
    growth_score = _mean_available([(production_score, 0.50), (orders_score, 0.25), (labor_score, 0.25)])

    liquidity_growth = _pct_change(walcl, 13)
    liquidity_score = _tanh_score(liquidity_growth, scale=8.0)

    rates_composite = _mean_available([(rate_score, 0.65), (curve_score, 0.35)])
    overall = _mean_available([
        (growth_score, 0.40),
        (rates_composite, 0.25),
        (liquidity_score, 0.15),
        (inflation_score, 0.20),
    ])
    return {
        "growth_score": growth_score,
        "rates_score": rates_composite,
        "liquidity_score": liquidity_score,
        "inflation_score": inflation_score,
        "overall_score": overall,
        "raw": {
            "dgs2_3m_change_pp": rate_3m_change,
            "yield_curve_10y2y": curve_latest,
            "cpi_yoy": cpi_yoy,
            "core_cpi_yoy": core_yoy,
            "unemployment_3m_change_pp": unrate_change,
            "payroll_6m_change": payroll_growth,
            "industrial_production_6m_change": indpro_growth,
            "durable_orders_6m_change": orders_growth,
            "fed_assets_13w_change": liquidity_growth,
        },
    }


def map_industry_scores(regime: dict[str, Any], sensitivity_cfg: dict[str, Any], industry_ids: list[str]) -> dict[str, float | None]:
    scores: dict[str, float | None] = {}
    profiles = sensitivity_cfg.get("profiles") or {}
    assignments = sensitivity_cfg.get("industry_profiles") or {}
    default_name = sensitivity_cfg.get("default", "balanced")
    for industry_id in industry_ids:
        profile_name = assignments.get(industry_id, default_name)
        profile = profiles.get(profile_name, profiles.get(default_name, {}))
        items = [
            (regime.get("growth_score"), float(profile.get("growth", 0))),
            (regime.get("rates_score"), float(profile.get("rates", 0))),
            (regime.get("liquidity_score"), float(profile.get("liquidity", 0))),
            (regime.get("inflation_score"), float(profile.get("inflation", 0))),
            (60.0, float(profile.get("defensive_base", 0))),
        ]
        scores[industry_id] = _mean_available(items)
    return scores


def collect(series_cfg: dict[str, Any], sensitivity_cfg: dict[str, Any], industry_ids: list[str]) -> dict[str, Any]:
    checked_at = _now()
    if not configured():
        return {
            "status": "MISSING_KEY",
            "checked_at": checked_at,
            "mapped_to_score": False,
            "needs_attention": True,
            "key_expiry_date": None,
            "renewal_status": "UNKNOWN",
            "series": {},
            "regime": {},
            "industry_macro_scores": {},
        }
    started = time.perf_counter()
    series_data: dict[str, list[dict[str, Any]]] = {}
    status: dict[str, Any] = {}
    errors: list[str] = []
    for series_id, meta in (series_cfg.get("series") or {}).items():
        try:
            rows = observations(series_id)
            series_data[series_id] = rows
            status[series_id] = {
                "status": "CONNECTED" if rows else "NO_DATA",
                "name_ko": meta.get("name_ko"),
                "records": len(rows),
                "latest_observation_date": rows[-1]["date"] if rows else None,
                "latest_value": rows[-1]["value"] if rows else None,
            }
        except Exception as exc:
            errors.append(f"{series_id}: {exc}")
            status[series_id] = {"status": "ERROR", "name_ko": meta.get("name_ko"), "message": str(exc)}
    regime = compute_regime(series_data)
    mapped = map_industry_scores(regime, sensitivity_cfg, industry_ids)
    successful = sum(1 for x in status.values() if x.get("status") == "CONNECTED")
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    overall_status = "CONNECTED" if successful == len(status) else "PARTIAL_SUCCESS" if successful else "ERROR"
    return {
        "status": overall_status,
        "checked_at": checked_at,
        "response_time_ms": elapsed_ms,
        "mapped_to_score": bool(mapped) and successful > 0,
        "needs_attention": overall_status != "CONNECTED",
        "key_expiry_date": None,
        "renewal_status": "NOT_EXPOSED_BY_API",
        "successful_series": successful,
        "total_series": len(status),
        "series": status,
        "regime": regime,
        "industry_macro_scores": mapped,
        "errors": errors,
    }
