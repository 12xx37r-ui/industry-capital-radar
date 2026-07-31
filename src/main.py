from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io_utils import load_json, write_json
from .pipeline import collect_live
from .scoring import score_industry

ROOT = Path(__file__).resolve().parents[1]
ENGINE_VERSION = "0.3.1"


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


def _api_status(source_status: dict[str, Any], now: str) -> dict[str, Any]:
    sources: dict[str, Any] = {}
    for source_name, raw in source_status.items():
        item = dict(raw or {})
        item.pop("series", None)
        item.pop("regime", None)
        sources[source_name] = item
    connected = sum(1 for item in sources.values() if str(item.get("status", "")).startswith("CONNECTED"))
    attention = [name for name, item in sources.items() if item.get("needs_attention")]
    return {
        "generated_at": now,
        "engine_version": ENGINE_VERSION,
        "connected_sources": connected,
        "total_sources": len(sources),
        "needs_attention": attention,
        "sources": sources,
        "renewal_note": "API가 만료일을 제공하지 않으면 갱신일은 UNKNOWN 또는 NOT_EXPOSED_BY_API로 표시합니다."
    }


def build_outputs(mode: str, skip_collect: bool = False) -> None:
    collection: dict[str, Any]
    if skip_collect:
        collection = {"skipped": True, "errors": [], "error_count": 0, "source_status": {}}
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
    features = load_features(ROOT / "data" / "normalized" / "industry_features.csv")
    evidence_path = ROOT / "data" / "evidence" / "industry_evidence.json"
    evidence = load_json(evidence_path) if evidence_path.exists() else {}
    industry_map = {item["id"]: item for item in industries_cfg["industries"]}
    now = datetime.now(timezone.utc).isoformat()

    radar_rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    unknown_industries: list[str] = []

    for row in features:
        industry_id = row["industry_id"]
        if industry_id not in industry_map:
            unknown_industries.append(industry_id)
            continue
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
        details[industry_id] = {
            "industry_name_ko": meta["name_ko"],
            "stage": scored["stage"],
            "scores": scored,
            "evidence": evidence.get(industry_id, {}),
            "warnings": [
                "대표기업 표본 기반 초기 신호이며 산업 전체 모집단을 완전히 대표하지 않습니다.",
                "점수는 백테스트로 보정된 확률이 아닙니다.",
                "ECOS·KOSIS 산업별 세부 통계는 아직 점수에 직접 매핑되지 않았습니다."
            ],
        }

    radar_rows.sort(
        key=lambda item: (item["lead_opportunity_score"] is not None, item["lead_opportunity_score"] or -1),
        reverse=True,
    )
    status = "PARTIAL_SUCCESS" if radar_rows else "NO_DATA"
    acceptable = [item for item in radar_rows if item["confidence_score"] >= 40]
    quality_gate = len(acceptable) >= 5
    source_status = collection.get("source_status") or {}

    write_json(ROOT / "public" / "industry_radar.json", {
        "generated_at": now,
        "engine_version": ENGINE_VERSION,
        "model_status": "EXPERIMENTAL_SCORE_NOT_PROBABILITY",
        "coverage_scope": "KR_REPRESENTATIVE_COMPANIES_PLUS_FRED_MACRO",
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
        "message": "한국 대표기업·시장·FRED 거시환경 기반 실험 점수 산출" if radar_rows else "실데이터 수집 또는 정규화 결과가 없습니다.",
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="manual", choices=["manual", "daily", "weekly", "monthly"])
    parser.add_argument("--skip-collect", action="store_true")
    args = parser.parse_args()
    build_outputs(args.mode, skip_collect=args.skip_collect)


if __name__ == "__main__":
    main()
