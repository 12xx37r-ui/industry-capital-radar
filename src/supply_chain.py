from __future__ import annotations

from collections import defaultdict
from typing import Any

from .quality import clamp


def compute_spillovers(
    scores: dict[str, dict[str, Any]],
    graph_cfg: dict[str, Any],
) -> tuple[dict[str, float | None], dict[str, list[dict[str, Any]]]]:
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph_cfg.get("edges") or []:
        source = str(edge.get("from", ""))
        target = str(edge.get("to", ""))
        weight = float(edge.get("weight", 0.0))
        source_score = (scores.get(source) or {}).get("boom_transition_12m_score")
        if source_score is None or not target or weight <= 0:
            continue
        incoming[target].append({
            "source_industry_id": source,
            "source_score": float(source_score),
            "weight": weight,
            "relation": edge.get("relation"),
            "contribution": float(source_score) * weight,
        })

    spillovers: dict[str, float | None] = {}
    evidence: dict[str, list[dict[str, Any]]] = {}
    for industry_id in scores:
        links = sorted(incoming.get(industry_id, []), key=lambda x: x["contribution"], reverse=True)
        if not links:
            spillovers[industry_id] = None
            evidence[industry_id] = []
            continue
        total_weight = sum(x["weight"] for x in links)
        spillovers[industry_id] = round(clamp(sum(x["contribution"] for x in links) / total_weight), 2)
        evidence[industry_id] = links[:5]
    return spillovers, evidence
