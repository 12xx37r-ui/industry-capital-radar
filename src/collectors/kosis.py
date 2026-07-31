"""KOSIS 공식 통계 검색·시계열 수집 및 산업별 한국 실물경기 매핑."""
from __future__ import annotations

import math
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from src.http_utils import HttpError, get_json
from src.quality import clamp

SEARCH_URL = "https://kosis.kr/openapi/statisticsSearch.do"
DATA_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
LIST_URL = "https://kosis.kr/openapi/statisticsList.do"


class KosisApiError(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.getenv("KOSIS_API_KEY", "").strip())


def _key() -> str:
    value = os.getenv("KOSIS_API_KEY", "").strip()
    if not value:
        raise KosisApiError("KOSIS_API_KEY is missing")
    return value


def _check(payload: Any) -> Any:
    if isinstance(payload, dict) and payload.get("err"):
        raise KosisApiError(str(payload.get("errMsg") or payload.get("err")))
    return payload


def search_tables(search_name: str, result_count: int = 10) -> list[dict[str, Any]]:
    payload = get_json(
        SEARCH_URL,
        {
            "method": "getList",
            "apiKey": _key(),
            "searchNm": search_name,
            "sort": "RANK",
            "startCount": "1",
            "resultCount": str(result_count),
            "format": "json",
            "jsonVD": "Y",
        },
        timeout=45,
        retries=2,
    )
    payload = _check(payload)
    return payload if isinstance(payload, list) else []


def parameter_data(org_id: str, tbl_id: str, prd_se: str, periods: int = 13) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "method": "getList",
        "apiKey": _key(),
        "orgId": org_id,
        "tblId": tbl_id,
        "objL1": "ALL",
        "itmId": "ALL",
        "prdSe": prd_se,
        "newEstPrdCnt": str(periods),
        "prdInterval": "1",
        "format": "json",
        "jsonVD": "Y",
        "smblChk": "N",
    }
    for level in range(2, 9):
        params[f"objL{level}"] = ""
    payload = get_json(DATA_URL, params, timeout=60, retries=2)
    payload = _check(payload)
    return payload if isinstance(payload, list) else []


def _number(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"-", "...", "..", "N/A"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _series_name(row: dict[str, Any]) -> str:
    pieces = [str(row.get("TBL_NM", "")), str(row.get("ITM_NM", ""))]
    for i in range(1, 9):
        pieces.append(str(row.get(f"C{i}_NM", "")))
    return " | ".join(x for x in pieces if x)


def group_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = _number(row.get("DT"))
        period = str(row.get("PRD_DE", ""))
        if value is None or not period:
            continue
        key = tuple(str(row.get(k, "")) for k in ["ITM_ID"] + [f"C{i}" for i in range(1, 9)])
        grouped[key].append({"period": period, "value": value, "raw": row})
    result: list[dict[str, Any]] = []
    for values in grouped.values():
        values.sort(key=lambda x: x["period"])
        first = values[-1]["raw"]
        result.append({
            "name": _series_name(first),
            "unit": first.get("UNIT_NM"),
            "rows": [{"time": x["period"], "value": x["value"]} for x in values],
        })
    return result


def _keyword_score(text: str, keywords: list[str]) -> int:
    compact = str(text).replace(" ", "").lower()
    score = 0
    for rank, keyword in enumerate(keywords):
        key = keyword.replace(" ", "").lower()
        if key and key in compact:
            score += max(1, 20 - rank * 3)
    if "전국" in text or "총지수" in text or "계" in text:
        score += 3
    return score


def choose_series(series: list[dict[str, Any]], keywords: list[str], exclude_keywords: list[str] | None = None) -> dict[str, Any] | None:
    exclude_keywords = exclude_keywords or []
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for item in series:
        name = str(item.get("name", ""))
        if any(x.replace(" ", "") in name.replace(" ", "") for x in exclude_keywords):
            continue
        score = _keyword_score(name, keywords)
        records = len(item.get("rows") or [])
        if records >= 3:
            candidates.append((score, records, item))
    return max(candidates, key=lambda x: (x[0], x[1]))[2] if candidates else None


def _pct(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return current / abs(previous) - 1.0


def series_signal(rows: list[dict[str, Any]], inverse: bool = False) -> dict[str, Any]:
    if len(rows) < 3:
        return {"score": None, "growth": None, "acceleration": None, "records": len(rows)}
    values = [float(x["value"]) for x in rows]
    horizon = min(6, max(1, len(values) // 3))
    prior_horizon = min(horizon, max(1, len(values) - horizon - 1))
    growth = _pct(values[-1], values[-1 - horizon])
    previous_growth = None
    if len(values) > horizon + prior_horizon:
        previous_growth = _pct(values[-1 - horizon], values[-1 - horizon - prior_horizon])
    acceleration = None if growth is None or previous_growth is None else growth - previous_growth
    sign = -1.0 if inverse else 1.0
    parts: list[tuple[float, float]] = []
    if growth is not None:
        parts.append((50 + 50 * math.tanh(sign * 8 * growth), 0.65))
    if acceleration is not None:
        parts.append((50 + 50 * math.tanh(sign * 10 * acceleration), 0.35))
    total = sum(w for _, w in parts)
    score = None if total <= 0 else clamp(sum(v * w for v, w in parts) / total)
    return {
        "score": round(score, 2) if score is not None else None,
        "growth": growth,
        "acceleration": acceleration,
        "records": len(rows),
        "latest_time": rows[-1]["time"],
        "latest_value": rows[-1]["value"],
    }


def _weighted(values: list[tuple[float | None, float]]) -> float | None:
    pairs = [(float(v), float(w)) for v, w in values if v is not None and w > 0]
    total = sum(w for _, w in pairs)
    return None if total <= 0 else round(clamp(sum(v * w for v, w in pairs) / total), 2)


def _fetch_best_table(search_terms: list[str], keywords: list[str]) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    candidates: list[dict[str, Any]] = []
    for term in search_terms:
        try:
            for row in search_tables(term, result_count=6):
                key = (str(row.get("ORG_ID", "")), str(row.get("TBL_ID", "")))
                if key not in seen and all(key):
                    seen.add(key)
                    candidates.append(row)
        except Exception as exc:
            errors.append(f"search {term}: {exc}")

    candidates.sort(key=lambda row: _keyword_score(str(row.get("TBL_NM", "")), keywords), reverse=True)
    for table in candidates[:5]:
        for cycle in ("M", "Q", "Y"):
            try:
                rows = parameter_data(str(table.get("ORG_ID")), str(table.get("TBL_ID")), cycle)
                if len(rows) >= 3:
                    return table, rows, errors
            except Exception as exc:
                errors.append(f"{table.get('TBL_ID')} {cycle}: {exc}")
    return None, [], errors


def map_industries(component_scores: dict[str, float | None], sensitivity_cfg: dict[str, Any], industry_ids: list[str]) -> dict[str, float | None]:
    profiles = sensitivity_cfg.get("profiles") or {}
    assignments = sensitivity_cfg.get("industry_profiles") or {}
    default_name = sensitivity_cfg.get("default", "balanced")
    out: dict[str, float | None] = {}
    for industry_id in industry_ids:
        profile = profiles.get(assignments.get(industry_id, default_name), profiles.get(default_name, {}))
        weights = profile.get("kosis_components") or {}
        out[industry_id] = _weighted([(component_scores.get(name), float(weight)) for name, weight in weights.items()])
    return out


def collect(series_cfg: dict[str, Any], sensitivity_cfg: dict[str, Any], industry_ids: list[str]) -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    if not configured():
        return {
            "status": "MISSING_KEY", "checked_at": checked_at, "mapped_to_score": False,
            "needs_attention": True, "key_expiry_date": None, "renewal_status": "UNKNOWN",
            "signals": {}, "industry_scores": {},
        }
    started = time.perf_counter()
    signals: dict[str, Any] = {}
    errors: list[str] = []

    for signal_id, cfg in ((series_cfg.get("kosis") or {}).get("signals") or {}).items():
        table, raw_rows, fetch_errors = _fetch_best_table(
            list(cfg.get("search_terms") or []), list(cfg.get("series_keywords") or [])
        )
        errors.extend(f"{signal_id}: {x}" for x in fetch_errors)
        if not table or not raw_rows:
            signals[signal_id] = {"status": "ERROR", "score": None, "message": "matching data not found"}
            continue
        grouped = group_series(raw_rows)
        if signal_id == "shipments_inventory":
            shipment = choose_series(grouped, ["출하지수", "출하", "제조업"], ["재고"])
            inventory = choose_series(grouped, ["재고지수", "재고", "제조업"], ["출하"])
            shipment_metric = series_signal((shipment or {}).get("rows") or [])
            inventory_metric = series_signal((inventory or {}).get("rows") or [], inverse=True)
            score = _weighted([(shipment_metric.get("score"), 0.60), (inventory_metric.get("score"), 0.40)])
            signals[signal_id] = {
                "status": "CONNECTED" if score is not None else "NO_DATA",
                "table_id": table.get("TBL_ID"), "table_name": table.get("TBL_NM"),
                "score": score,
                "shipment_series": (shipment or {}).get("name"),
                "inventory_series": (inventory or {}).get("name"),
                "shipment_metric": shipment_metric,
                "inventory_metric": inventory_metric,
            }
        else:
            chosen = choose_series(grouped, list(cfg.get("series_keywords") or []))
            metric = series_signal((chosen or {}).get("rows") or [])
            signals[signal_id] = {
                "status": "CONNECTED" if metric.get("score") is not None else "NO_DATA",
                "table_id": table.get("TBL_ID"), "table_name": table.get("TBL_NM"),
                "series_name": (chosen or {}).get("name"),
                **metric,
            }

    component_scores = {name: item.get("score") for name, item in signals.items()}
    industry_scores = map_industries(component_scores, sensitivity_cfg, industry_ids)
    successful = sum(1 for item in signals.values() if item.get("status") == "CONNECTED")
    status = "CONNECTED" if successful == len(signals) and signals else "PARTIAL_SUCCESS" if successful else "ERROR"
    return {
        "status": status,
        "checked_at": checked_at,
        "response_time_ms": round((time.perf_counter() - started) * 1000),
        "mapped_to_score": successful > 0 and bool(industry_scores),
        "needs_attention": successful == 0,
        "key_expiry_date": None,
        "renewal_status": "NOT_EXPOSED_BY_API",
        "successful_signals": successful,
        "total_signals": len(signals),
        "signals": signals,
        "industry_scores": industry_scores,
        "errors": errors[:50],
    }


def health() -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    if not configured():
        return {
            "status": "MISSING_KEY", "checked_at": checked_at, "mapped_to_score": False,
            "needs_attention": True, "key_expiry_date": None, "renewal_status": "UNKNOWN"
        }
    started = time.perf_counter()
    payload = get_json(
        LIST_URL,
        {
            "method": "getList", "apiKey": _key(), "vwCd": "MT_ZTITLE",
            "parentId": "", "format": "json", "jsonVD": "Y",
        },
        timeout=45,
        retries=2,
    )
    _check(payload)
    count = len(payload) if isinstance(payload, list) else 0
    return {
        "status": "CONNECTED_NOT_MAPPED", "checked_at": checked_at,
        "response_time_ms": round((time.perf_counter() - started) * 1000),
        "root_items": count, "mapped_to_score": False, "needs_attention": False,
        "key_expiry_date": None, "renewal_status": "NOT_EXPOSED_BY_API",
    }
