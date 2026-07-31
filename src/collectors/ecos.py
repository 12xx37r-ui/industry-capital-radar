"""한국은행 ECOS connection health collector."""
from __future__ import annotations

import os
from typing import Any

from src.http_utils import get_json


def configured() -> bool:
    return bool(os.getenv("ECOS_API_KEY"))


def health() -> dict[str, Any]:
    key = os.getenv("ECOS_API_KEY", "").strip()
    if not key:
        return {"status": "MISSING_KEY", "mapped_to_score": False}
    url = f"https://ecos.bok.or.kr/api/StatisticTableList/{key}/json/kr/1/1"
    payload = get_json(url, retries=1)
    if "RESULT" in payload:
        result = payload["RESULT"]
        return {"status": "ERROR", "code": result.get("CODE"), "message": result.get("MESSAGE"), "mapped_to_score": False}
    count = ((payload.get("StatisticTableList") or {}).get("list_total_count"))
    return {"status": "CONNECTED_NOT_MAPPED", "table_count": count, "mapped_to_score": False}
