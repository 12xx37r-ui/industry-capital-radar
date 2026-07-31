"""KOSIS connection health collector."""
from __future__ import annotations

import os
from typing import Any

from src.http_utils import get_json


def configured() -> bool:
    return bool(os.getenv("KOSIS_API_KEY"))


def health() -> dict[str, Any]:
    key = os.getenv("KOSIS_API_KEY", "").strip()
    if not key:
        return {"status": "MISSING_KEY", "mapped_to_score": False}
    payload = get_json("https://kosis.kr/openapi/statisticsList.do", {
        "method": "getList", "apiKey": key, "vwCd": "MT_ZTITLE",
        "parentListId": "A", "format": "json", "jsonVD": "Y",
    }, retries=1)
    if isinstance(payload, dict) and payload.get("err"):
        return {"status": "ERROR", "message": payload.get("err"), "mapped_to_score": False}
    return {"status": "CONNECTED_NOT_MAPPED", "root_items": len(payload) if isinstance(payload, list) else None, "mapped_to_score": False}
