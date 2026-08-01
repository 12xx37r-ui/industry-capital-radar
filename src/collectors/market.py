"""Optional market-price proxy using Yahoo chart JSON. Non-official auxiliary source."""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from src.http_utils import get_json

BASE = "https://query1.finance.yahoo.com/v8/finance/chart"


def history(symbol: str, days: int = 420) -> list[dict[str, float]]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    payload = get_json(f"{BASE}/{symbol}", {
        "period1": int(start.timestamp()), "period2": int(now.timestamp()),
        "interval": "1d", "events": "history", "includeAdjustedClose": "true",
    }, headers={"User-Agent": "Mozilla/5.0 industry-capital-radar/0.5.0"}, retries=1)
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        return []
    timestamps = result.get("timestamp") or []
    quote = (((result.get("indicators") or {}).get("quote") or [{}])[0])
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    rows = []
    for ts, close, volume in zip(timestamps, closes, volumes):
        if close is None:
            continue
        rows.append({"ts": float(ts), "close": float(close), "volume": float(volume or 0)})
    return rows


def summarize(rows: list[dict[str, float]]) -> dict[str, float | None]:
    if len(rows) < 80:
        return {"return_6m": None, "return_12m": None, "volume_acceleration": None, "latest_ts": None, "latest_price": None}
    closes = [x["close"] for x in rows]
    current = closes[-1]
    lookback_6m = min(126, len(closes) - 1)
    lookback_12m = min(252, len(closes) - 1)
    return_6m = current / closes[-1 - lookback_6m] - 1 if closes[-1 - lookback_6m] else None
    return_12m = current / closes[-1 - lookback_12m] - 1 if closes[-1 - lookback_12m] else None
    recent_vol = [x["volume"] for x in rows[-40:] if x["volume"] > 0]
    prior_vol = [x["volume"] for x in rows[-160:-40] if x["volume"] > 0]
    volume_acc = None
    if recent_vol and prior_vol:
        base = statistics.median(prior_vol)
        if base > 0:
            volume_acc = statistics.median(recent_vol) / base - 1
    return {
        "return_6m": return_6m,
        "return_12m": return_12m,
        "volume_acceleration": volume_acc,
        "latest_ts": rows[-1]["ts"],
        "latest_price": current,
    }
