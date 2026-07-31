from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io_utils import load_json, write_json
from .scoring import score_industry

ROOT = Path(__file__).resolve().parents[1]


def _to_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
            for k, v in raw.items():
                if k not in {"industry_id", "as_of_date"}:
                    row[k] = _to_float(v)
            rows.append(row)
        return rows


def build_outputs(mode: str) -> None:
    industries_cfg = load_json(ROOT / "config" / "industries.json")
    weights_cfg = load_json(ROOT / "config" / "model_weights.json")
    features = load_features(ROOT / "data" / "normalized" / "industry_features.csv")
    industry_map = {x["id"]: x for x in industries_cfg["industries"]}
    now = datetime.now(timezone.utc).isoformat()

    radar_rows = []
    details: dict[str, Any] = {}
    unknown_industries = []

    for row in features:
        industry_id = row["industry_id"]
        if industry_id not in industry_map:
            unknown_industries.append(industry_id)
            continue
        scored = score_industry(row, weights_cfg)
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
            "evidence": [],
            "warnings": ["원천 근거 문장과 출처 연결은 수집기 구현 후 활성화됩니다."],
        }

    radar_rows.sort(key=lambda x: x["lead_opportunity_score"], reverse=True)
    status = "SUCCESS" if radar_rows else "NO_DATA"

    write_json(ROOT / "public" / "industry_radar.json", {
        "generated_at": now,
        "engine_version": "0.1.0",
        "model_status": "EXPERIMENTAL_SCORE_NOT_PROBABILITY",
        "run_mode": mode,
        "status": status,
        "industries": radar_rows,
    })
    write_json(ROOT / "public" / "industry_detail.json", {
        "generated_at": now,
        "engine_version": "0.1.0",
        "industries": details,
    })
    write_json(ROOT / "public" / "engine_status.json", {
        "generated_at": now,
        "engine_version": "0.1.0",
        "run_mode": mode,
        "run_status": status,
        "rows_loaded": len(features),
        "rows_scored": len(radar_rows),
        "unknown_industries": sorted(set(unknown_industries)),
        "quality_gate_passed": bool(radar_rows),
        "message": "정규화 입력 데이터가 필요합니다." if not radar_rows else "점수 산출 완료",
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="manual", choices=["manual", "daily", "weekly", "monthly"])
    args = parser.parse_args()
    build_outputs(args.mode)


if __name__ == "__main__":
    main()
