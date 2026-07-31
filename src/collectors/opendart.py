"""OpenDART live collector for annual financial statements, employees and disclosure counts."""
from __future__ import annotations

import io
import os
import re
import zipfile
from datetime import date, timedelta
from typing import Any
from xml.etree import ElementTree as ET

from src.http_utils import get_bytes, get_json

BASE = "https://opendart.fss.or.kr/api"
REPORT_ANNUAL = "11011"


class DartApiError(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.getenv("OPENDART_API_KEY"))


def _key() -> str:
    value = os.getenv("OPENDART_API_KEY", "").strip()
    if not value:
        raise DartApiError("OPENDART_API_KEY is missing")
    return value


def _check(payload: dict[str, Any], allow_no_data: bool = False) -> dict[str, Any]:
    status = str(payload.get("status", ""))
    if status == "000":
        return payload
    if allow_no_data and status in {"013", "014"}:
        return {**payload, "list": []}
    raise DartApiError(f"OpenDART status={status}: {payload.get('message')}")


def corp_code_map() -> dict[str, dict[str, str]]:
    raw = get_bytes(f"{BASE}/corpCode.xml", {"crtfc_key": _key()}, timeout=60)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            xml_name = next(name for name in zf.namelist() if name.lower().endswith(".xml"))
            root = ET.fromstring(zf.read(xml_name))
    except (zipfile.BadZipFile, StopIteration, ET.ParseError) as exc:
        raise DartApiError("corpCode response is not a valid ZIP/XML; check API key") from exc
    result: dict[str, dict[str, str]] = {}
    for item in root.findall("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        if not stock_code:
            continue
        result[stock_code.zfill(6)] = {
            "corp_code": (item.findtext("corp_code") or "").strip(),
            "corp_name": (item.findtext("corp_name") or "").strip(),
            "modify_date": (item.findtext("modify_date") or "").strip(),
        }
    return result


def financial_accounts(corp_code: str, year: int) -> list[dict[str, Any]]:
    common = {
        "crtfc_key": _key(), "corp_code": corp_code, "bsns_year": str(year),
        "reprt_code": REPORT_ANNUAL,
    }
    for fs_div in ("CFS", "OFS"):
        payload = get_json(f"{BASE}/fnlttSinglAcntAll.json", {**common, "fs_div": fs_div})
        checked = _check(payload, allow_no_data=True)
        rows = checked.get("list") or []
        if rows:
            return rows
    return []


def employee_status(corp_code: str, year: int) -> list[dict[str, Any]]:
    payload = get_json(f"{BASE}/empSttus.json", {
        "crtfc_key": _key(), "corp_code": corp_code, "bsns_year": str(year),
        "reprt_code": REPORT_ANNUAL,
    })
    return _check(payload, allow_no_data=True).get("list") or []


def disclosure_list(corp_code: str, begin: date, end: date) -> list[dict[str, Any]]:
    payload = get_json(f"{BASE}/list.json", {
        "crtfc_key": _key(), "corp_code": corp_code,
        "bgn_de": begin.strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"),
        "last_reprt_at": "Y", "page_no": "1", "page_count": "100",
    })
    return _check(payload, allow_no_data=True).get("list") or []


def disclosure_signal_counts(corp_code: str, end: date | None = None) -> dict[str, int]:
    end = end or date.today()
    curr_begin = end - timedelta(days=365)
    prev_end = curr_begin - timedelta(days=1)
    prev_begin = prev_end - timedelta(days=365)
    keywords = {
        "orders": ("단일판매", "공급계약", "수주"),
        "capex": ("신규시설투자", "시설투자", "유형자산 양수", "유형자산취득"),
    }
    out: dict[str, int] = {}
    for label, begin, finish in (("curr", curr_begin, end), ("prev", prev_begin, prev_end)):
        rows = disclosure_list(corp_code, begin, finish)
        for kind, words in keywords.items():
            out[f"{kind}_{label}"] = sum(
                1 for row in rows
                if any(word in str(row.get("report_nm", "")) for word in words)
            )
    return out


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "null", "None"}:
        return None
    text = re.sub(r"[^0-9.\-]", "", text)
    if text in {"", "-", "."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _best_account(rows: list[dict[str, Any]], patterns: tuple[str, ...], sj_div: str | None = None,
                  exclude: tuple[str, ...] = ()) -> float | None:
    candidates: list[tuple[int, float]] = []
    for row in rows:
        if sj_div and str(row.get("sj_div")) != sj_div:
            continue
        name = str(row.get("account_nm", "")).replace(" ", "")
        if any(x.replace(" ", "") in name for x in exclude):
            continue
        matched = next((p for p in patterns if p.replace(" ", "") in name), None)
        if not matched:
            continue
        value = _number(row.get("thstrm_amount"))
        if value is None:
            continue
        exact_bonus = 100 if name == matched.replace(" ", "") else 0
        candidates.append((exact_bonus - len(name), value))
    return max(candidates, key=lambda x: x[0])[1] if candidates else None


def extract_metrics(rows: list[dict[str, Any]], employees: list[dict[str, Any]]) -> dict[str, float | None]:
    revenue = _best_account(rows, ("매출액", "영업수익", "수익(매출액)", "매출"), "IS", ("매출원가",))
    op_income = _best_account(rows, ("영업이익", "영업이익(손실)"), "IS")
    inventory = _best_account(rows, ("재고자산",), "BS")
    ppe = _best_account(rows, ("유형자산",), "BS", ("투자부동산",))
    capex = _best_account(rows, ("유형자산의취득", "유형자산취득", "유형자산의증가"), "CF")
    if capex is not None:
        capex = abs(capex)
    employee_total = 0.0
    employee_seen = False
    for row in employees:
        for key in ("sm", "rgllbr_co", "cnttk_co"):
            val = _number(row.get(key))
            if val is not None:
                employee_seen = True
                employee_total += val
                if key == "sm":
                    break
    return {
        "revenue": revenue,
        "operating_income": op_income,
        "inventory": inventory,
        "ppe": ppe,
        "capex": capex,
        "employees": employee_total if employee_seen else None,
    }
