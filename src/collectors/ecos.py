"""한국은행 ECOS connection health collector."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from src.http_utils import get_json


def configured() -> bool:
    return bool(os.getenv("ECOS_API_KEY", "").strip())


def health() -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    key = os.getenv("ECOS_API_KEY", "").strip()
    if not key:
        return {
            "status": "MISSING_KEY", "checked_at": checked_at, "mapped_to_score": False,
            "needs_attention": True, "key_expiry_date": None, "renewal_status": "UNKNOWN"
        }
    started = time.perf_counter()
    url = f"https://ecos.bok.or.kr/api/StatisticTableList/{key}/json/kr/1/1"
    payload = get_json(url, retries=1)
    elapsed = round((time.perf_counter() - started) * 1000)
    if "RESULT" in payload:
        result = payload["RESULT"]
        return {
            "status": "ERROR", "checked_at": checked_at, "response_time_ms": elapsed,
            "code": result.get("CODE"), "message": result.get("MESSAGE"), "mapped_to_score": False,
            "needs_attention": True, "key_expiry_date": None, "renewal_status": "UNKNOWN"
        }
    count = ((payload.get("StatisticTableList") or {}).get("list_total_count"))
    return {
        "status": "CONNECTED_NOT_MAPPED", "checked_at": checked_at, "response_time_ms": elapsed,
        "table_count": count, "mapped_to_score": False, "needs_attention": False,
        "key_expiry_date": None, "renewal_status": "NOT_EXPOSED_BY_API"
    }
