"""KOSIS connection health collector."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from src.http_utils import get_json


def configured() -> bool:
    return bool(os.getenv("KOSIS_API_KEY", "").strip())


def health() -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    key = os.getenv("KOSIS_API_KEY", "").strip()
    if not key:
        return {
            "status": "MISSING_KEY", "checked_at": checked_at, "mapped_to_score": False,
            "needs_attention": True, "key_expiry_date": None, "renewal_status": "UNKNOWN"
        }
    started = time.perf_counter()
    payload = get_json("https://kosis.kr/openapi/statisticsList.do", {
        "method": "getList", "apiKey": key, "vwCd": "MT_ZTITLE",
        "parentListId": "A", "format": "json", "jsonVD": "Y",
    }, retries=1)
    elapsed = round((time.perf_counter() - started) * 1000)
    if isinstance(payload, dict) and payload.get("err"):
        return {
            "status": "ERROR", "checked_at": checked_at, "response_time_ms": elapsed,
            "message": payload.get("err"), "mapped_to_score": False, "needs_attention": True,
            "key_expiry_date": None, "renewal_status": "UNKNOWN"
        }
    return {
        "status": "CONNECTED_NOT_MAPPED", "checked_at": checked_at, "response_time_ms": elapsed,
        "root_items": len(payload) if isinstance(payload, list) else None, "mapped_to_score": False,
        "needs_attention": False, "key_expiry_date": None, "renewal_status": "NOT_EXPOSED_BY_API"
    }
