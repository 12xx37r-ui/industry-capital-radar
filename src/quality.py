from __future__ import annotations


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def quality_score(row: dict[str, float]) -> float:
    coverage = clamp(row.get("source_coverage", 0.0))
    freshness = clamp(row.get("freshness_score", 0.0))
    reliability = clamp(row.get("source_reliability", 0.0))
    return round(0.45 * coverage + 0.25 * freshness + 0.30 * reliability, 2)


def quality_label(score: float) -> str:
    if score >= 80:
        return "GOOD"
    if score >= 60:
        return "ACCEPTABLE"
    if score >= 40:
        return "LOW"
    return "INSUFFICIENT"
