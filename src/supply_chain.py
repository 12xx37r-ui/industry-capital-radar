from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from .quality import clamp


def _source_trigger(score: dict[str, Any]) -> float | None:
    parts: list[tuple[float, float]] = []
    for key, weight in (
        ("capital_acceleration_score", 0.45),
        ("demand_validation_score", 0.25),
        ("boom_transition_12m_score", 0.20),
        ("underrecognition_score", 0.10),
    ):
        value = score.get(key)
        if isinstance(value, (int, float)):
            parts.append((float(value), weight))
    if not parts:
        fallback = score.get("boom_transition_12m_score")
        return float(fallback) if isinstance(fallback, (int, float)) else None
    total = sum(w for _, w in parts)
    return clamp(sum(v * w for v, w in parts) / total)


def compute_spillovers(
    scores: dict[str, dict[str, Any]],
    graph_cfg: dict[str, Any],
) -> tuple[
    dict[str, float | None],
    dict[str, float | None],
    dict[str, list[dict[str, Any]]],
]:
    edges = [
        {
            "from": str(edge.get("from", "")),
            "to": str(edge.get("to", "")),
            "weight": float(edge.get("weight", 0.0)),
            "relation": edge.get("relation"),
        }
        for edge in graph_cfg.get("edges") or []
        if edge.get("from") and edge.get("to") and float(edge.get("weight", 0.0)) > 0
    ]
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        outgoing[edge["from"]].append(edge)

    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    # Direct first-hop propagation.
    for edge in edges:
        source = edge["from"]
        target = edge["to"]
        trigger = _source_trigger(scores.get(source) or {})
        if trigger is None or target not in scores:
            continue
        weight = edge["weight"]
        incoming[target].append({
            "source_industry_id": source,
            "via_industry_id": None,
            "hop": 1,
            "source_trigger_score": round(trigger, 2),
            "weight": weight,
            "relation": edge.get("relation"),
            "contribution": trigger * weight,
        })

    # Two-hop propagation catches second/third-order beneficiaries before the
    # crowd focuses on them. Decay prevents distant paths from dominating.
    decay = float(graph_cfg.get("second_hop_decay", 0.45))
    for first in edges:
        origin = first["from"]
        mid = first["to"]
        trigger = _source_trigger(scores.get(origin) or {})
        if trigger is None:
            continue
        for second in outgoing.get(mid, []):
            target = second["to"]
            if target not in scores or target in {origin, mid}:
                continue
            weight = first["weight"] * second["weight"] * decay
            if weight <= 0:
                continue
            incoming[target].append({
                "source_industry_id": origin,
                "via_industry_id": mid,
                "hop": 2,
                "source_trigger_score": round(trigger, 2),
                "weight": round(weight, 4),
                "relation": f"{first.get('relation')} → {second.get('relation')}",
                "contribution": trigger * weight,
            })

    spillovers: dict[str, float | None] = {}
    breadth_scores: dict[str, float | None] = {}
    evidence: dict[str, list[dict[str, Any]]] = {}
    for industry_id in scores:
        links = incoming.get(industry_id, [])
        # Keep the strongest path from the same origin/hop to avoid cycle inflation.
        deduped: dict[tuple[str, int], dict[str, Any]] = {}
        for link in links:
            key = (str(link["source_industry_id"]), int(link["hop"]))
            if key not in deduped or link["contribution"] > deduped[key]["contribution"]:
                deduped[key] = link
        ranked = sorted(deduped.values(), key=lambda x: x["contribution"], reverse=True)
        if not ranked:
            spillovers[industry_id] = None
            breadth_scores[industry_id] = None
            evidence[industry_id] = []
            continue
        total_weight = sum(float(x["weight"]) for x in ranked)
        spillovers[industry_id] = round(
            clamp(sum(float(x["contribution"]) for x in ranked) / total_weight),
            2,
        )
        distinct_sources = len({x["source_industry_id"] for x in ranked})
        direct_sources = len({x["source_industry_id"] for x in ranked if x["hop"] == 1})
        breadth = 100.0 * (1.0 - math.exp(-distinct_sources / 2.5))
        if direct_sources == 0:
            breadth *= 0.80
        breadth_scores[industry_id] = round(clamp(breadth), 2)
        evidence[industry_id] = [
            {
                **link,
                "contribution": round(float(link["contribution"]), 2),
            }
            for link in ranked[:8]
        ]
    return spillovers, breadth_scores, evidence
