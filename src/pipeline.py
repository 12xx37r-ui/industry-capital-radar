from __future__ import annotations

import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .collectors import ecos, fred, kosis, market, opendart
from .io_utils import load_json, write_json
from .normalize import build_industry_features
from .quality import clamp

ROOT = Path(__file__).resolve().parents[1]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "industry_id", "as_of_date", "capital_level", "capital_velocity", "capital_acceleration",
        "orders_velocity", "backlog_acceleration", "capacity_tightness", "hiring_velocity",
        "innovation_velocity", "official_activity", "breadth", "persistence", "macro_fit",
        "supply_chain_spillover", "supply_chain_breadth", "market_attention", "price_momentum", "valuation_heat",
        "valuation_attractiveness", "valuation_data_confidence", "supply_overbuild_risk", "policy_dependency_risk",
        "source_coverage", "freshness_score", "source_reliability"
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "" if row.get(k) is None else row.get(k) for k in headers})


def _load_cached_companies() -> tuple[list[dict[str, Any]], str | None]:
    path = ROOT / "data" / "snapshots" / "company_metrics.json"
    if not path.exists():
        return [], None
    try:
        payload = load_json(path)
        companies = payload.get("companies") or []
        generated_at = payload.get("generated_at")
        return companies if isinstance(companies, list) else [], generated_at
    except Exception:
        return [], None


def _cache_age_days(generated_at: str | None) -> int | None:
    if not generated_at:
        return None
    try:
        dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        try:
            d = date.fromisoformat(generated_at[:10])
            return (date.today() - d).days
        except Exception:
            return None


def _collect_company_full(entry: dict[str, Any], corp: dict[str, str], years: list[int]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    company: dict[str, Any] = {**entry, "corp_code": corp["corp_code"], "annual": {}}
    for year in years:
        try:
            rows = opendart.financial_accounts(corp["corp_code"], year)
            emp = opendart.employee_status(corp["corp_code"], year)
            if rows or emp:
                company["annual"][str(year)] = opendart.extract_metrics(rows, emp)
        except Exception as exc:
            errors.append(f"DART {entry['stock_code']} {year}: {exc}")
    try:
        company["shares"] = opendart.stock_status(corp["corp_code"], years[0])
    except Exception as exc:
        company["shares"] = {}
        errors.append(f"DART shares {entry['stock_code']}: {exc}")
    try:
        company["disclosures"] = opendart.disclosure_signal_counts(corp["corp_code"])
    except Exception as exc:
        company["disclosures"] = {}
        errors.append(f"DART disclosures {entry['stock_code']}: {exc}")
    return company, errors


def _refresh_disclosures(company: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    copied = dict(company)
    try:
        copied["disclosures"] = opendart.disclosure_signal_counts(str(company.get("corp_code", "")))
        return copied, None
    except Exception as exc:
        return copied, f"DART disclosures {company.get('stock_code')}: {exc}"


def _refresh_market(company: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    copied = dict(company)
    symbol = copied.get("yahoo_symbol")
    if not symbol:
        copied["market"] = {}
        return copied, None
    try:
        copied["market"] = market.summarize(market.history(symbol))
        return copied, None
    except Exception as exc:
        copied["market"] = {}
        return copied, f"Market {symbol}: {exc}"


def _weighted(values: list[tuple[float | None, float]]) -> float | None:
    pairs = [(float(v), float(w)) for v, w in values if isinstance(v, (int, float)) and w > 0]
    total = sum(w for _, w in pairs)
    return None if total <= 0 else round(clamp(sum(v * w for v, w in pairs) / total), 2)


def _combine_macro_scores(
    industry_ids: list[str],
    fred_scores: dict[str, float | None],
    ecos_scores: dict[str, float | None],
    kosis_scores: dict[str, float | None],
    sensitivity_cfg: dict[str, Any],
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    profiles = sensitivity_cfg.get("profiles") or {}
    assignments = sensitivity_cfg.get("industry_profiles") or {}
    default_name = sensitivity_cfg.get("default", "balanced")
    macro: dict[str, float | None] = {}
    official: dict[str, float | None] = {}
    for industry_id in industry_ids:
        profile = profiles.get(assignments.get(industry_id, default_name), profiles.get(default_name, {}))
        macro[industry_id] = _weighted([
            (fred_scores.get(industry_id), float(profile.get("fred", 0.0))),
            (ecos_scores.get(industry_id), float(profile.get("ecos", 0.0))),
            (kosis_scores.get(industry_id), float(profile.get("kosis", 0.0))),
        ])
        official[industry_id] = _weighted([
            (ecos_scores.get(industry_id), float(profile.get("ecos", 0.0))),
            (kosis_scores.get(industry_id), float(profile.get("kosis", 0.0))),
        ])
    return macro, official


def _collect_macro(industry_ids: list[str]) -> tuple[dict[str, Any], dict[str, float | None], dict[str, float | None]]:
    macro_cfg = load_json(ROOT / "config" / "korean_macro_series.json")
    sensitivity_cfg = load_json(ROOT / "config" / "korean_industry_sensitivity.json")
    jobs = {
        "fred": lambda: fred.collect(
            load_json(ROOT / "config" / "fred_series.json"),
            load_json(ROOT / "config" / "industry_macro_sensitivity.json"),
            industry_ids,
        ),
        "ecos": lambda: ecos.collect(macro_cfg, sensitivity_cfg, industry_ids),
        "kosis": lambda: kosis.collect(macro_cfg, sensitivity_cfg, industry_ids),
    }
    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {executor.submit(fn): name for name, fn in jobs.items()}
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                results[name] = {
                    "status": "ERROR", "message": str(exc), "mapped_to_score": False,
                    "needs_attention": True, "checked_at": datetime.now(timezone.utc).isoformat(),
                    "industry_scores": {}, "industry_macro_scores": {},
                }

    fred_scores = (results.get("fred") or {}).get("industry_macro_scores") or {}
    ecos_scores = (results.get("ecos") or {}).get("industry_scores") or {}
    kosis_scores = (results.get("kosis") or {}).get("industry_scores") or {}
    macro_scores, official_scores = _combine_macro_scores(
        industry_ids, fred_scores, ecos_scores, kosis_scores, sensitivity_cfg
    )
    return results, macro_scores, official_scores


def collect_live(mode: str) -> dict[str, Any]:
    started_total = time.perf_counter()
    universe = load_json(ROOT / "config" / "company_universe.json")["companies"]
    industries = [x["id"] for x in load_json(ROOT / "config" / "industries.json")["industries"]]
    source_status: dict[str, Any] = {}
    errors: list[str] = []

    macro_results, macro_scores, official_scores = _collect_macro(industries)
    source_status.update(macro_results)

    cached_companies, cache_generated_at = _load_cached_companies()
    cache_age = _cache_age_days(cache_generated_at)
    use_full_dart = mode == "monthly" or not cached_companies or cache_age is None or cache_age >= 30
    refresh_disclosures = mode in {"weekly", "monthly"}
    companies: list[dict[str, Any]] = []

    if not opendart.configured():
        source_status["opendart"] = {
            "status": "MISSING_KEY", "mapped_to_score": True, "needs_attention": True,
            "checked_at": datetime.now(timezone.utc).isoformat(), "cache_used": bool(cached_companies)
        }
        companies = cached_companies
    elif use_full_dart:
        dart_started = time.perf_counter()
        try:
            corp_map = opendart.corp_code_map()
            latest_year = date.today().year - 1
            years = [latest_year, latest_year - 1, latest_year - 2]
            jobs: list[tuple[dict[str, Any], dict[str, str]]] = []
            for entry in universe:
                corp = corp_map.get(entry["stock_code"])
                if not corp:
                    errors.append(f"DART corp_code missing: {entry['stock_code']} {entry['name']}")
                else:
                    jobs.append((entry, corp))
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [executor.submit(_collect_company_full, entry, corp, years) for entry, corp in jobs]
                for future in as_completed(futures):
                    company, company_errors = future.result()
                    if company:
                        companies.append(company)
                    errors.extend(company_errors)
            companies.sort(key=lambda x: x.get("stock_code", ""))
            source_status["opendart"] = {
                "status": "CONNECTED", "checked_at": datetime.now(timezone.utc).isoformat(),
                "response_time_ms": round((time.perf_counter() - dart_started) * 1000),
                "listed_corporations": len(corp_map), "companies_collected": len(companies),
                "mapped_to_score": True, "needs_attention": False, "refresh_mode": "FULL",
                "cache_used": False, "key_expiry_date": None, "renewal_status": "NOT_EXPOSED_BY_API"
            }
        except Exception as exc:
            errors.append(f"OpenDART fatal: {exc}")
            companies = cached_companies
            source_status["opendart"] = {
                "status": "ERROR_USING_CACHE" if cached_companies else "ERROR",
                "message": str(exc), "mapped_to_score": True, "needs_attention": True,
                "checked_at": datetime.now(timezone.utc).isoformat(), "cache_used": bool(cached_companies),
                "cache_generated_at": cache_generated_at
            }
    else:
        companies = cached_companies
        if refresh_disclosures:
            refreshed: list[dict[str, Any]] = []
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [executor.submit(_refresh_disclosures, c) for c in companies]
                for future in as_completed(futures):
                    company, error = future.result()
                    refreshed.append(company)
                    if error:
                        errors.append(error)
            companies = sorted(refreshed, key=lambda x: x.get("stock_code", ""))
        source_status["opendart"] = {
            "status": "CONNECTED_CACHE", "checked_at": datetime.now(timezone.utc).isoformat(),
            "mapped_to_score": True, "needs_attention": False,
            "refresh_mode": "DISCLOSURES_ONLY" if refresh_disclosures else "CACHE_ONLY",
            "cache_used": True, "cache_generated_at": cache_generated_at, "cache_age_days": cache_age,
            "companies_collected": len(companies), "key_expiry_date": None,
            "renewal_status": "NOT_EXPOSED_BY_API"
        }

    market_started = time.perf_counter()
    refreshed_market: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_refresh_market, company) for company in companies]
        for future in as_completed(futures):
            company, error = future.result()
            refreshed_market.append(company)
            if error:
                errors.append(error)
    companies = sorted(refreshed_market, key=lambda x: x.get("stock_code", ""))
    market_success = sum(1 for c in companies if (c.get("market") or {}).get("return_6m") is not None)
    source_status["market_proxy"] = {
        "status": "CONNECTED" if market_success else "NO_DATA",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "response_time_ms": round((time.perf_counter() - market_started) * 1000),
        "successful_symbols": market_success, "total_symbols": len(companies),
        "official": False, "mapped_to_score": True, "needs_attention": market_success == 0,
        "key_expiry_date": None, "renewal_status": "NOT_APPLICABLE"
    }

    rows, evidence = build_industry_features(
        companies, industries, macro_scores=macro_scores, official_scores=official_scores
    )
    _write_csv(ROOT / "data" / "normalized" / "industry_features.csv", rows)
    now = datetime.now(timezone.utc).isoformat()
    write_json(ROOT / "data" / "snapshots" / "company_metrics.json", {"generated_at": now, "companies": companies})
    write_json(ROOT / "data" / "snapshots" / "macro_sources.json", {
        "generated_at": now,
        "sources": source_status,
        "industry_macro_scores": macro_scores,
        "industry_official_activity_scores": official_scores,
    })
    write_json(ROOT / "data" / "evidence" / "industry_evidence.json", evidence)
    write_json(ROOT / "data" / "snapshots" / "source_status.json", source_status)
    return {
        "companies_collected": len(companies),
        "industries_normalized": len(rows),
        "source_status": source_status,
        "errors": errors[:100],
        "error_count": len(errors),
        "elapsed_seconds": round(time.perf_counter() - started_total, 2),
        "cache": {
            "used": not use_full_dart and bool(cached_companies),
            "previous_generated_at": cache_generated_at,
            "previous_age_days": cache_age,
            "dart_refresh": "FULL" if use_full_dart else "DISCLOSURES_ONLY" if refresh_disclosures else "CACHE_ONLY"
        }
    }
