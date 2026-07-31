from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from .collectors import ecos, kosis, market, opendart
from .io_utils import load_json, write_json
from .normalize import build_industry_features

ROOT = Path(__file__).resolve().parents[1]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    import csv
    headers = [
        "industry_id","as_of_date","capital_level","capital_velocity","capital_acceleration",
        "orders_velocity","backlog_acceleration","capacity_tightness","hiring_velocity",
        "innovation_velocity","policy_funding_velocity","breadth","persistence","macro_fit",
        "market_attention","price_momentum","valuation_heat","supply_overbuild_risk",
        "policy_dependency_risk","source_coverage","freshness_score","source_reliability"
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "" if row.get(k) is None else row.get(k) for k in headers})


def collect_live(mode: str) -> dict[str, Any]:
    universe = load_json(ROOT / "config" / "company_universe.json")["companies"]
    industries = [x["id"] for x in load_json(ROOT / "config" / "industries.json")["industries"]]
    source_status: dict[str, Any] = {}
    companies: list[dict[str, Any]] = []
    errors: list[str] = []

    # Key health for sources not yet mapped into scores.
    for name, fn in (("ecos", ecos.health), ("kosis", kosis.health)):
        try:
            source_status[name] = fn()
        except Exception as exc:  # source failure must not destroy DART baseline
            source_status[name] = {"status": "ERROR", "message": str(exc), "mapped_to_score": False}

    if not opendart.configured():
        source_status["opendart"] = {"status": "MISSING_KEY", "mapped_to_score": True}
    else:
        try:
            corp_map = opendart.corp_code_map()
            source_status["opendart"] = {"status": "CONNECTED", "listed_corporations": len(corp_map), "mapped_to_score": True}
            latest_year = date.today().year - 1
            years = [latest_year, latest_year - 1, latest_year - 2]
            for entry in universe:
                stock_code = entry["stock_code"]
                corp = corp_map.get(stock_code)
                if not corp:
                    errors.append(f"DART corp_code missing: {stock_code} {entry['name']}")
                    continue
                company: dict[str, Any] = {**entry, "corp_code": corp["corp_code"], "annual": {}}
                for year in years:
                    try:
                        rows = opendart.financial_accounts(corp["corp_code"], year)
                        emp = opendart.employee_status(corp["corp_code"], year)
                        if rows or emp:
                            company["annual"][str(year)] = opendart.extract_metrics(rows, emp)
                    except Exception as exc:
                        errors.append(f"DART {stock_code} {year}: {exc}")
                try:
                    company["disclosures"] = opendart.disclosure_signal_counts(corp["corp_code"])
                except Exception as exc:
                    company["disclosures"] = {}
                    errors.append(f"DART disclosures {stock_code}: {exc}")
                companies.append(company)
        except Exception as exc:
            source_status["opendart"] = {"status": "ERROR", "message": str(exc), "mapped_to_score": True}
            errors.append(f"OpenDART fatal: {exc}")

    # Optional market proxy. Each symbol failure is isolated.
    market_success = 0
    for company in companies:
        symbol = company.get("yahoo_symbol")
        if not symbol:
            continue
        try:
            company["market"] = market.summarize(market.history(symbol))
            if company["market"].get("return_6m") is not None:
                market_success += 1
        except Exception as exc:
            company["market"] = {}
            errors.append(f"Market {symbol}: {exc}")
    source_status["market_proxy"] = {
        "status": "CONNECTED" if market_success else "NO_DATA",
        "successful_symbols": market_success,
        "total_symbols": len(companies),
        "official": False,
        "mapped_to_score": True,
    }

    rows, evidence = build_industry_features(companies, industries)
    _write_csv(ROOT / "data" / "normalized" / "industry_features.csv", rows)
    write_json(ROOT / "data" / "snapshots" / "company_metrics.json", {
        "generated_at": date.today().isoformat(), "companies": companies,
    })
    write_json(ROOT / "data" / "evidence" / "industry_evidence.json", evidence)
    write_json(ROOT / "data" / "snapshots" / "source_status.json", source_status)
    return {
        "companies_collected": len(companies), "industries_normalized": len(rows),
        "source_status": source_status, "errors": errors[:100], "error_count": len(errors),
    }
