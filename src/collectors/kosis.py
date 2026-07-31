"""KOSIS connection health collector."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from src.http_utils import HttpError, get_json


KOSIS_LIST_URL = "https://kosis.kr/openapi/statisticsList.do"


def configured() -> bool:
    return bool(os.getenv("KOSIS_API_KEY", "").strip())


def health() -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    key = os.getenv("KOSIS_API_KEY", "").strip()
    if not key:
        return {
            "status": "MISSING_KEY",
            "checked_at": checked_at,
            "mapped_to_score": False,
            "needs_attention": True,
            "key_expiry_date": None,
            "renewal_status": "UNKNOWN",
        }

    started = time.perf_counter()
    try:
        # KOSIS 공식 통계목록 API의 요청변수는 parentId입니다.
        # 루트 목록만 조회해 인증키와 서비스 연결 상태를 가볍게 확인합니다.
        payload = get_json(
            KOSIS_LIST_URL,
            {
                "method": "getList",
                "apiKey": key,
                "vwCd": "MT_ZTITLE",
                "parentId": "",
                "format": "json",
                "jsonVD": "Y",
            },
            timeout=45,
            retries=3,
        )
        elapsed = round((time.perf_counter() - started) * 1000)
    except HttpError as exc:
        return {
            "status": "TEMPORARY_ERROR",
            "message": str(exc),
            "mapped_to_score": False,
            "needs_attention": True,
            "checked_at": checked_at,
            "response_time_ms": round((time.perf_counter() - started) * 1000),
            "key_expiry_date": None,
            "renewal_status": "UNKNOWN",
        }

    if isinstance(payload, dict) and payload.get("err"):
        return {
            "status": "ERROR",
            "checked_at": checked_at,
            "response_time_ms": elapsed,
            "message": str(payload.get("err")),
            "mapped_to_score": False,
            "needs_attention": True,
            "key_expiry_date": None,
            "renewal_status": "UNKNOWN",
        }

    if not isinstance(payload, list):
        return {
            "status": "UNEXPECTED_RESPONSE",
            "checked_at": checked_at,
            "response_time_ms": elapsed,
            "mapped_to_score": False,
            "needs_attention": True,
            "key_expiry_date": None,
            "renewal_status": "UNKNOWN",
        }

    return {
        "status": "CONNECTED_NOT_MAPPED",
        "checked_at": checked_at,
        "response_time_ms": elapsed,
        "root_items": len(payload),
        "mapped_to_score": False,
        "needs_attention": False,
        "key_expiry_date": None,
        "renewal_status": "NOT_EXPOSED_BY_API",
    }
