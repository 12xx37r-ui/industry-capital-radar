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
ENGINE_VERSION = "0.5.0"


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
    for key in (
        "series", "regime", "signals", "industry_scores",
        "industry_macro_scores", "errors", "warnings",
    ):
        item.pop(key, None)
    return item


def _api_status(source_status: dict[str, Any], now: str) -> dict[str, Any]:
    sources = {name: _compact_source(raw) for name, raw in source_status.items()}
    connected = sum(
        1 for item in sources.values()
        if str(item.get("status", "")).startswith(("CONNECTED", "PARTIAL_SUCCESS"))
    )
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
        "renewal_note": "API가 만료일을 제공하지 않으면 갱신일은 UNKNOWN 또는 NOT_EXPOSED_BY_API로 표시합니다.",
    }


def _load_history() -> dict[str, Any]:
    path = ROOT / "data" / "history" / "industry_history.json"
    if not path.exists():
        return {"version": "1", "snapshots": []}
    try:
        payload = load_json(path)
        if not isinstance(payload, dict) or not isinstance(payload.get("snapshots"), list):
            return {"version": "1", "snapshots": []}
        return payload
    except Exception:
        return {"version": "1", "snapshots": []}


def _previous_comparable_snapshot(history: dict[str, Any]) -> dict[str, Any] | None:
    for snapshot in reversed(history.get("snapshots") or []):
        if snapshot.get("engine_version") == ENGINE_VERSION:
            return snapshot
    return None


def _attach_trends(radar_rows: list[dict[str, Any]], previous: dict[str, Any] | None) -> None:
    previous_rows = (previous or {}).get("industries") or {}
    for row in radar_rows:
        old = previous_rows.get(row["industry_id"]) or {}
        comparable = bool(old)
        row["history_comparable"] = comparable
        row["pre_boom_change_vs_previous"] = (
            round(float(row["pre_boom_pattern_score"]) - float(old["pre_boom_pattern_score"]), 2)
            if comparable
            and isinstance(row.get("pre_boom_pattern_score"), (int, float))
            and isinstance(old.get("pre_boom_pattern_score"), (int, float))
            else None
        )
        row["capital_acceleration_change_vs_previous"] = (
            round(float(row["capital_acceleration_score"]) - float(old["capital_acceleration_score"]), 2)
            if comparable
            and isinstance(row.get("capital_acceleration_score"), (int, float))
            and isinstance(old.get("capital_acceleration_score"), (int, float))
            else None
        )
        row["market_heat_change_vs_previous"] = (
            round(float(row["market_heat_score"]) - float(old["market_heat_score"]), 2)
            if comparable
            and isinstance(row.get("market_heat_score"), (int, float))
            and isinstance(old.get("market_heat_score"), (int, float))
            else None
        )


def _append_history(history: dict[str, Any], radar_rows: list[dict[str, Any]], now: str) -> None:
    snapshot = {
        "generated_at": now,
        "engine_version": ENGINE_VERSION,
        "industries": {
            row["industry_id"]: {
                "pre_boom_pattern_score": row.get("pre_boom_pattern_score"),
                "capital_acceleration_score": row.get("capital_acceleration_score"),
                "market_heat_score": row.get("market_heat_score"),
                "real_economy_confirmation_score": row.get("real_economy_confirmation_score"),
                "candidate_tier": row.get("candidate_tier"),
            }
            for row in radar_rows
        },
    }
    snapshots = list(history.get("snapshots") or [])
    snapshots.append(snapshot)
    history["version"] = "1"
    history["snapshots"] = snapshots[-180:]
    write_json(ROOT / "data" / "history" / "industry_history.json", history)


def _next_ai_candidates(top10: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [item for item in top10 if item.get("candidate_tier") in {"A", "B"}]
    return candidates[:10]


def build_outputs(mode: str, skip_collect: bool = False) -> None:
    if skip_collect:
        collection: dict[str, Any] = {"skipped": True, "errors": [], "error_count": 0, "source_status": {}}
    else:
        try:
            collection = collect_live(mode)
        except Exception as exc:
            collection = {
                "fatal_error": str(exc),
                "errors": [str(exc)],
                "error_count": 1,
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

    first_scores = {
        industry_id: score_industry(row, weights_cfg)
        for industry_id, row in valid_rows.items()
    }
    spillovers, supply_breadth, supply_evidence = compute_spillovers(first_scores, graph_cfg)
    for industry_id, row in valid_rows.items():
        row["supply_chain_spillover"] = spillovers.get(industry_id)
        row["supply_chain_breadth"] = supply_breadth.get(industry_id)
        populated = [
            "capital_level", "capital_velocity", "capital_acceleration", "orders_velocity",
            "backlog_acceleration", "capacity_tightness", "hiring_velocity", "innovation_velocity",
            "official_activity", "breadth", "persistence", "macro_fit", "supply_chain_spillover",
            "supply_chain_breadth", "market_attention", "price_momentum", "valuation_heat",
            "valuation_attractiveness", "valuation_data_confidence", "supply_overbuild_risk",
            "policy_dependency_risk",
        ]
        row["source_coverage"] = round(
            100 * sum(row.get(k) is not None for k in populated) / len(populated),
            2,
        )
    _write_csv(features_path, list(valid_rows.values()))

    radar_rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for industry_id, row in valid_rows.items():
        scored = score_industry(row, weights_cfg)
        if scored["pre_boom_pattern_score"] is None:
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
            "candidate_tier": scored["candidate_tier"],
            "next_ai_candidate": scored["next_ai_candidate"],
            "scores": scored,
            "evidence": ev,
            "warnings": [
                "대표기업 표본 기반 초기 신호이며 산업 전체 모집단을 완전히 대표하지 않습니다.",
                "pre_boom_pattern_score는 백테스트로 보정된 확률이 아닙니다.",
                "P/E·P/B는 DART 연차자료와 최근 보조주가로 계산한 근사치입니다.",
                "특허·정부예산·공공조달 원문은 아직 직접 연결되지 않았습니다.",
            ],
        }

    history = _load_history()
    previous = _previous_comparable_snapshot(history)
    _attach_trends(radar_rows, previous)
    radar_rows.sort(
        key=lambda item: (
            item.get("candidate_tier") == "A",
            item.get("candidate_tier") == "B",
            item.get("pre_boom_pattern_score") is not None,
            item.get("pre_boom_pattern_score") or -1,
            item.get("lead_opportunity_score") or -1,
        ),
        reverse=True,
    )
    top10 = build_top10(radar_rows, details)
    next_ai = _next_ai_candidates(top10)
    _append_history(history, radar_rows, now)

    status = "SUCCESS" if radar_rows and not collection.get("fatal_error") else "PARTIAL_SUCCESS" if radar_rows else "NO_DATA"
    acceptable = [item for item in radar_rows if item["confidence_score"] >= 60]
    source_status = collection.get("source_status") or {}
    attention_sources = [name for name, item in source_status.items() if item.get("needs_attention")]
    source_integrity_gate = len(attention_sources) == 0
    quality_gate = len(acceptable) >= 5 and source_integrity_gate

    write_json(ROOT / "public" / "industry_radar.json", {
        "generated_at": now,
        "engine_version": ENGINE_VERSION,
        "model_status": "EXPERIMENTAL_PRE_BOOM_SCORE_NOT_PROBABILITY",
        "coverage_scope": "KR_REPRESENTATIVE_COMPANIES_PLUS_ECOS_KOSIS_FRED_TWO_HOP_SUPPLY_CHAIN",
        "run_mode": mode,
        "status": status,
        "quality_gate_passed": quality_gate,
        "source_integrity_gate_passed": source_integrity_gate,
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
        "model_status": "EXPERIMENTAL_PRE_BOOM_SCORE_NOT_PROBABILITY",
        "valuation_note": "기업 저평가는 근사 P/E·P/B와 시장 미반영 신호이며 최종 적정가가 아닙니다.",
        "ranking_note": "실물자금 가속·수요확인·시장 미인지·1~2차 공급망 확산을 우선하며 선반영·가치함정을 감점합니다.",
        "opportunities": top10,
    })
    write_json(ROOT / "public" / "next_ai_candidates.json", {
        "generated_at": now,
        "engine_version": ENGINE_VERSION,
        "model_status": "EXPERIMENTAL_PRE_BOOM_SCORE_NOT_PROBABILITY",
        "candidate_rule": "Tier A/B이며 실물경제 확인점수 50 이상인 산업",
        "candidates": next_ai,
    })
    write_json(ROOT / "public" / "supply_chain_radar.json", {
        "generated_at": now,
        "engine_version": ENGINE_VERSION,
        "method": "DIRECT_AND_SECOND_HOP_WITH_DECAY",
        "spillovers": spillovers,
        "breadth": supply_breadth,
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
        "source_integrity_gate_passed": source_integrity_gate,
        "attention_sources": attention_sources,
        "history_comparison_available": previous is not None,
        "collection": collection,
        "outputs": [
            "industry_radar.json",
            "industry_detail.json",
            "opportunity_top10.json",
            "next_ai_candidates.json",
            "supply_chain_radar.json",
            "engine_status.json",
            "api_status.json",
        ],
        "message": (
            "실물자금 가속·시장 미인지 괴리·2단계 공급망 확산 기반 선행 산업 점수 산출"
            if radar_rows else "실데이터 수집 또는 정규화 결과가 없습니다."
        ),
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="manual", choices=["manual", "daily", "weekly", "monthly"])
    parser.add_argument("--skip-collect", action="store_true")
    args = parser.parse_args()
    build_outputs(args.mode, skip_collect=args.skip_collect)


if __name__ == "__main__":
    main()
