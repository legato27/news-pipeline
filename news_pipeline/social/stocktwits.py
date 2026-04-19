"""StockTwits sentiment fetcher.

Extracted from Project-StockPrediction/.../services/sentiment/stocktwits.py.
No credentials required (public API).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx


logger = logging.getLogger(__name__)

STOCKTWITS_BASE = "https://api.stocktwits.com/api/2"


async def fetch_ticker_sentiment(ticker: str, *, limit: int = 30, timeout: float = 15.0) -> dict:
    """Fetch bullish/bearish ratio and message volume from StockTwits."""
    ticker = ticker.upper()

    try:
        url = f"{STOCKTWITS_BASE}/streams/symbol/{ticker}.json"
        params = {"limit": limit}

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        messages = data.get("messages", [])
        if not messages:
            return {"ticker": ticker, "score": 0.0, "bull_pct": 0.5, "message_volume": 0}

        bull = sum(
            1 for m in messages
            if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bullish"
        )
        bear = sum(
            1 for m in messages
            if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bearish"
        )
        neutral = len(messages) - bull - bear

        total = len(messages)
        bull_pct = bull / total if total > 0 else 0.5
        score = (bull - bear) / (bull + bear + 1)

        symbol_info = data.get("symbol", {})
        total_volume = symbol_info.get("watchlist_count", total)

        return {
            "ticker": ticker,
            "score": round(float(score), 4),
            "bull_pct": round(float(bull_pct), 4),
            "bull_count": bull,
            "bear_count": bear,
            "neutral_count": neutral,
            "message_volume": total_volume,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"ticker": ticker, "score": 0.0, "error": "ticker not found on StockTwits"}
        logger.error("stocktwits_http_error ticker=%s err=%s", ticker, e)
        return {"ticker": ticker, "score": 0.0, "error": str(e)}
    except Exception as e:
        logger.error("stocktwits_error ticker=%s err=%s", ticker, e)
        return {"ticker": ticker, "score": 0.0, "error": str(e)}
