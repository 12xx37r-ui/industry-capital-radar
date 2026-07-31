"""OpenDART collector boundary.

v0.1에서는 API 계약만 고정한다. API 키는 환경변수 OPENDART_API_KEY에서 읽고,
시설투자·정기보고서·직원현황·재무정보 매핑은 다음 버전에서 구현한다.
"""
from __future__ import annotations

import os


def configured() -> bool:
    return bool(os.getenv("OPENDART_API_KEY"))
