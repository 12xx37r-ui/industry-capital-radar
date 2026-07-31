"""한국은행 ECOS 시계열 수집 및 산업별 한국 거시 적합도 매핑."""
from __future__ import annotations

import math
import os
import time
from datetime import datetime, timezone
from typing import Any

from src.http_utils import get_json
from src.quality import clamp

BASE = "https://ecos.bok.or.kr/api"


class EcosApiError(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.getenv("ECOS_API_KEY", "").strip())


def _key() -> str:
    value = os.getenv("ECOS_API_KEY", "").strip()
    if not value:
        raise EcosApiError("ECOS_API_KEY is missing")
    return value


def _rows(payload: dict[str, Any], service: str) -> list[dict[str, Any]]:
    if "RESULT" in payload:
        result = payload.get("RESULT") or {}
        raise EcosApiError(f"ECOS {result.get('CODE')}: {result.get('MESSAGE')}")
    body = payload.get(service) or {}
    result = body.get("RESULT") or {}
    if result and result.get("CODE") not in (None, "INFO-000"):
        raise EcosApiError(f"ECOS {result.get('CODE')}: {result.get('MESSAGE')}")
    rows = body.get("row") or []
    return rows if isinstance(rows, list) else []


def table_list(limit: int = 1200) -> list[dict[str, Any]]:
    payload = get_json(f"{BASE}/StatisticTableList/{_key()}/json/kr/1/{limit}", timeout=45, retries=2)
    return _rows(payload, "StatisticTableList")


def item_list(stat_code: str, limit: int = 1000) -> list[dict[str, Any]]:
    payload = get_json(
        f"{BASE}/StatisticItemList/{_key()}/json/kr/1/{limit}/{stat_code}",
        timeout=45,
        retries=2,
    )
    return _rows(payload, "StatisticItemList")


def observations(stat_code: str, cycle: str, start: str, end: str, item_code: str, limit: int = 1000) -> list[dict[str, Any]]:
    url = f"{BASE}/StatisticSearch/{_key()}/json/kr/1/{limit}/{stat_code}/{cycle}/{start}/{end}/{item_code}"
    payload = get_json(url, timeout=45, retries=2)
    raw = _rows(payload, "StatisticSearch")
    rows: list[dict[str, Any]] = []
    for item in raw:
        try:
            value = float(str(item.get("DATA_VALUE", "")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        rows.append({"time": str(item.get("TIME", "")), "value": value})
    rows.sort(key=lambda x: x["time"])
    return rows


def _text_score(text: str, keywords: list[str]) -> int:
    compact = str(text).replace(" ", "").lower()
    score = 0
    for rank, keyword in enumerate(keywords):
        key = keyword.replace(" ", "").lower()
        if key and key in compact:
            score += max(1, 20 - rank * 3)
    return score


def discover_table(tables: list[dict[str, Any]], keywords: list[str]) -> dict[str, Any] | None:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for row in tables:
        if str(row.get("SRCH_YN", "Y")) != "Y":
            continue
        score = _text_score(str(row.get("STAT_NAME", "")), keywords)
        if score > 0:
            cycle = str(row.get("CYCLE", ""))
            score += 8 if cycle == "M" else 5 if cycle == "Q" else 2 if cycle in {"A", "Y"} else 0
            candidates.append((score, row))
    return max(candidates, key=lambda x: x[0])[1] if candidates else None


def discover_item(items: list[dict[str, Any]], keywords: list[str]) -> dict[str, Any] | None:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for row in items:
        name = " ".join(str(row.get(k, "")) for k in ("ITEM_NAME", "ITEM_NAME1", "ITEM_NAME2", "ITEM_NAME3"))
        score = _text_score(name, keywords)
        cycle = str(row.get("CYCLE", ""))
        score += 8 if cycle == "M" else 5 if cycle == "Q" else 2 if cycle in {"A", "Y"} else 0
        end_time = str(row.get("END_TIME", ""))
        if end_time:
            score += 2
        candidates.append((score, row))
    return max(candidates, key=lambda x: x[0])[1] if candidates else None


def _date_window(cycle: str, end_time: str | None) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    end = (end_time or "").strip()
    if cycle == "D":
        end = end if len(end) == 8 else now.strftime("%Y%m%d")
        return str(int(end[:4]) - 2) + end[4:], end
    if cycle == "M":
        end = end if len(end) >= 6 else now.strftime("%Y%m")
        return str(int(end[:4]) - 4) + end[4:6], end[:6]
    if cycle == "Q":
        if len(end) >= 6 and "Q" in end.upper():
            end_q = end.upper()[:6]
        elif len(end) >= 5 and end[4:].isdigit():
            end_q = f"{end[:4]}Q{end[-1]}"
        else:
            end_q = f"{now.year}Q4"
        return f"{int(end_q[:4]) - 5}Q1", end_q
    end = end[:4] if len(end) >= 4 else str(now.year)
    return str(int(end) - 10), end


def _pct(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return current / abs(previous) - 1.0


def series_signal(rows: list[dict[str, Any]], direction: str = "positive") -> dict[str, Any]:
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
    sign = -1.0 if direction == "negative" else 1.0
    parts = []
    if growth is not None:
        parts.append((50 + 50 * math.tanh(sign * 8.0 * growth), 0.65))
    if acceleration is not None:
        parts.append((50 + 50 * math.tanh(sign * 10.0 * acceleration), 0.35))
    total = sum(w for _, w in parts)
    score = None if not parts else clamp(sum(v * w for v, w in parts) / total)
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


def map_industries(component_scores: dict[str, float | None], sensitivity_cfg: dict[str, Any], industry_ids: list[str]) -> dict[str, float | None]:
    profiles = sensitivity_cfg.get("profiles") or {}
    assignments = sensitivity_cfg.get("industry_profiles") or {}
    default_name = sensitivity_cfg.get("default", "balanced")
    out: dict[str, float | None] = {}
    for industry_id in industry_ids:
        profile = profiles.get(assignments.get(industry_id, default_name), profiles.get(default_name, {}))
        weights = profile.get("ecos_components") or {}
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
    try:
        tables = table_list()
    except Exception as exc:
        return {
            "status": "ERROR", "message": str(exc), "checked_at": checked_at,
            "mapped_to_score": False, "needs_attention": True,
            "key_expiry_date": None, "renewal_status": "UNKNOWN",
            "signals": {}, "industry_scores": {},
        }

    signals: dict[str, Any] = {}
    errors: list[str] = []
    for signal_id, cfg in ((series_cfg.get("ecos") or {}).get("signals") or {}).items():
        try:
            table = discover_table(tables, list(cfg.get("table_keywords") or []))
            if not table:
                raise EcosApiError("matching table not found")
            stat_code = str(table.get("STAT_CODE", ""))
            items = item_list(stat_code)
            item = discover_item(items, list(cfg.get("item_keywords") or []))
            if not item:
                raise EcosApiError("matching item not found")
            cycle = str(item.get("CYCLE") or table.get("CYCLE") or "M")
            item_code = str(item.get("ITEM_CODE", ""))
            start, end = _date_window(cycle, str(item.get("END_TIME", "")))
            rows = observations(stat_code, cycle, start, end, item_code)
            metric = series_signal(rows, str(cfg.get("direction", "positive")))
            signals[signal_id] = {
                "status": "CONNECTED" if metric.get("score") is not None else "NO_DATA",
                "table_code": stat_code,
                "table_name": table.get("STAT_NAME"),
                "item_code": item_code,
                "item_name": item.get("ITEM_NAME"),
                "cycle": cycle,
                **metric,
            }
        except Exception as exc:
            errors.append(f"{signal_id}: {exc}")
            signals[signal_id] = {"status": "ERROR", "message": str(exc), "score": None}

    component_scores = {name: item.get("score") for name, item in signals.items()}
    industry_scores = map_industries(component_scores, sensitivity_cfg, industry_ids)
    successful = sum(1 for item in signals.values() if item.get("status") == "CONNECTED")
    status = "CONNECTED" if successful == len(signals) and signals else "PARTIAL_SUCCESS" if successful else "ERROR"
    return {
        "status": status,
        "checked_at": checked_at,
        "response_time_ms": round((time.perf_counter() - started) * 1000),
        "table_count": len(tables),
        "mapped_to_score": successful > 0 and bool(industry_scores),
        "needs_attention": successful == 0,
        "key_expiry_date": None,
        "renewal_status": "NOT_EXPOSED_BY_API",
        "successful_signals": successful,
        "total_signals": len(signals),
        "signals": signals,
        "industry_scores": industry_scores,
        "errors": errors,
    }


def health() -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    if not configured():
        return {
            "status": "MISSING_KEY", "checked_at": checked_at, "mapped_to_score": False,
            "needs_attention": True, "key_expiry_date": None, "renewal_status": "UNKNOWN"
        }
    started = time.perf_counter()
    tables = table_list(limit=1)
    return {
        "status": "CONNECTED_NOT_MAPPED", "checked_at": checked_at,
        "response_time_ms": round((time.perf_counter() - started) * 1000),
        "table_count": len(tables), "mapped_to_score": False, "needs_attention": False,
        "key_expiry_date": None, "renewal_status": "NOT_EXPOSED_BY_API"
    }
