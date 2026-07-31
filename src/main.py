from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io_utils import load_json, write_json
from .opportunities import build_top10
from .pipeline import _write_csv, collect_live
from .scoring import score_industry
from .supply_chain import compute_spillovers

ROOT = Path(__file__).resolve().parents[1]
ENGINE_VERSION = "0.4.0"


def _to_float(value: str | None) -> float | None:
    if value is None or not str(value).strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_features(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = []
        for raw in csv.DictReader(f):
            if not raw.get("industry_id"):
                continue
            row: dict[str, Any] = {
                "industry_id": raw["industry_id"].strip(),
                "as_of_date": raw.get("as_of_date", "").strip(),
            }
            for key, value in raw.items():
                if key not in {"industry_id", "as_of_date"}:
                    row[key] = _to_float(value)
            rows.append(row)
        return rows


def _compact_source(raw: dict[str, Any]) -> dict[str, Any]:
    item = dict(raw or {})
    for key in ("series", "regime", "signals", "industry_scores", "industry_macro_scores", "errors"):
        item.pop(key, None)
    return item


def _api_status(source_status: dict[str, Any], now: str) -> dict[str, Any]:
    sources = {name: _compact_source(raw) for name, raw in source_status.items()}
    connected = sum(1 for item in sources.values() if str(item.get("status", "")).startswith(("CONNECTED", "PARTIAL_SUCCESS")))
    attention = [name for name, item in sources.items() if item.get("needs_attention")]
    mapped = [name for name, item in sources.items() if item.get("mapped_to_score")]
    return {
        "generated_at": now,
        "engine_version": ENGINE_VERSION,
        "connected_sources": connected,
        "total_sources": len(sources),
        "mapped_sources": mapped,
        "needs_attention": attention,
        "sources": sources,
        "renewal_note": "API가 만료일을 제공하지 않으면 갱신일은 UNKNOWN 또는 NOT_EXPOSED_BY_API로 표시합니다."
    }


def build_outputs(mode: str, skip_collect: bool = False) -> None:
    if skip_collect:
        collection: dict[str, Any] = {"skipped": True, "errors": [], "error_count": 0, "source_status": {}}
    else:
        try:
            collection = collect_live(mode)
        except Exception as exc:
            collection = {
                "fatal_error": str(exc), "errors": [str(exc)], "error_count": 1,
                "source_status": {},
            }

    industries_cfg = load_json(ROOT / "config" / "industries.json")
    weights_cfg = load_json(ROOT / "config" / "model_weights.json")
    graph_cfg = load_json(ROOT / "config" / "supply_chain_graph.json")
    features_path = ROOT / "data" / "normalized" / "industry_features.csv"
    features = load_features(features_path)
    evidence_path = ROOT / "data" / "evidence" / "industry_evidence.json"
    evidence = load_json(evidence_path) if evidence_path.exists() else {}
    industry_map = {item["id"]: item for item in industries_cfg["industries"]}
    now = datetime.now(timezone.utc).isoformat()

    valid_rows: dict[str, dict[str, Any]] = {}
    unknown_industries: list[str] = []
    for row in features:
        industry_id = row["industry_id"]
        if industry_id not in industry_map:
            unknown_industries.append(industry_id)
            continue
        valid_rows[industry_id] = row

    first_scores = {industry_id: score_industry(row, weights_cfg) for industry_id, row in valid_rows.items()}
    spillovers, supply_evidence = compute_spillovers(first_scores, graph_cfg)
    for industry_id, row in valid_rows.items():
        row["supply_chain_spillover"] = spillovers.get(industry_id)
        populated = [
            "capital_level", "capital_velocity", "capital_acceleration", "orders_velocity",
            "backlog_acceleration", "capacity_tightness", "hiring_velocity", "innovation_velocity",
            "official_activity", "breadth", "persistence", "macro_fit", "supply_chain_spillover",
            "market_attention", "price_momentum", "valuation_heat", "valuation_attractiveness",
            "supply_overbuild_risk", "policy_dependency_risk",
        ]
        row["source_coverage"] = round(100 * sum(row.get(k) is not None for k in populated) / len(populated), 2)
    _write_csv(features_path, list(valid_rows.values()))

    radar_rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for industry_id, row in valid_rows.items():
        scored = score_industry(row, weights_cfg)
        if scored["boom_transition_12m_score"] is None:
            continue
        meta = industry_map[industry_id]
        result = {
            "industry_id": industry_id,
            "industry_name_ko": meta["name_ko"],
            "parent": meta["parent"],
            "as_of_date": row.get("as_of_date"),
            **scored,
        }
        radar_rows.append(result)
        ev = dict(evidence.get(industry_id, {}))
        ev["supply_chain_incoming"] = supply_evidence.get(industry_id, [])
        details[industry_id] = {
            "industry_name_ko": meta["name_ko"],
            "stage": scored["stage"],
            "scores": scored,
            "evidence": ev,
            "warnings": [
                "대표기업 표본 기반 초기 신호이며 산업 전체 모집단을 완전히 대표하지 않습니다.",
                "점수는 백테스트로 보정된 확률이 아닙니다.",
                "P/E·P/B는 DART 연차자료와 최근 보조주가로 계산한 근사치입니다."
            ],
        }

    radar_rows.sort(
        key=lambda item: (item["lead_opportunity_score"] is not None, item["lead_opportunity_score"] or -1),
        reverse=True,
    )
    top10 = build_top10(radar_rows, details)
    status = "PARTIAL_SUCCESS" if radar_rows else "NO_DATA"
    acceptable = [item for item in radar_rows if item["confidence_score"] >= 60]
    quality_gate = len(acceptable) >= 5
    source_status = collection.get("source_status") or {}

    write_json(ROOT / "public" / "industry_radar.json", {
        "generated_at": now,
        "engine_version": ENGINE_VERSION,
        "model_status": "EXPERIMENTAL_SCORE_NOT_PROBABILITY",
        "coverage_scope": "KR_REPRESENTATIVE_COMPANIES_PLUS_ECOS_KOSIS_FRED_SUPPLY_CHAIN",
        "run_mode": mode,
        "status": status,
        "quality_gate_passed": quality_gate,
        "industries": radar_rows,
    })
    write_json(ROOT / "public" / "industry_detail.json", {
        "generated_at": now,
        "engine_version": ENGINE_VERSION,
        "industries": details,
    })
    write_json(ROOT / "public" / "opportunity_top10.json", {
        "generated_at": now,
        "engine_version": ENGINE_VERSION,
        "model_status": "EXPERIMENTAL_SCORE_NOT_PROBABILITY",
        "valuation_note": "기업 저평가는 근사 P/E·P/B와 시장 미반영 신호이며 최종 적정가가 아닙니다.",
        "opportunities": top10,
    })
    write_json(ROOT / "public" / "supply_chain_radar.json", {
        "generated_at": now,
        "engine_version": ENGINE_VERSION,
        "spillovers": spillovers,
        "incoming_evidence": supply_evidence,
    })
    write_json(ROOT / "public" / "api_status.json", _api_status(source_status, now))
    write_json(ROOT / "public" / "engine_status.json", {
        "generated_at": now,
        "engine_version": ENGINE_VERSION,
        "run_mode": mode,
        "run_status": status,
        "rows_loaded": len(features),
        "rows_scored": len(radar_rows),
        "acceptable_quality_rows": len(acceptable),
        "unknown_industries": sorted(set(unknown_industries)),
        "quality_gate_passed": quality_gate,
        "collection": collection,
        "outputs": [
            "industry_radar.json", "industry_detail.json", "opportunity_top10.json",
            "supply_chain_radar.json", "engine_status.json", "api_status.json"
        ],
        "message": "한국 대표기업·공식통계·글로벌 거시·공급망 기반 실험 점수 산출" if radar_rows else "실데이터 수집 또는 정규화 결과가 없습니다.",
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="manual", choices=["manual", "daily", "weekly", "monthly"])
    parser.add_argument("--skip-collect", action="store_true")
    args = parser.parse_args()
    build_outputs(args.mode, skip_collect=args.skip_collect)


if __name__ == "__main__":
    main()
