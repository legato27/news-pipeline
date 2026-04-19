"""Finnhub social sentiment wrapper.

Primary social provider per the plan (no credentials beyond FINNHUB_API_KEY).
Thin wrapper around ingest.finnhub.fetch_market_sentiment that normalizes the
output shape.
"""
from __future__ import annotations

from news_pipeline.ingest.finnhub import fetch_market_sentiment


def fetch_ticker_sentiment(ticker: str, *, api_key: str) -> dict:
    """Fetch Finnhub's aggregated Reddit + Twitter buzz for a ticker.

    Returns Finnhub's raw response verbatim when available. Empty dict on failure.
    """
    raw = fetch_market_sentiment(ticker, api_key=api_key)
    if not raw:
        return {"ticker": ticker, "score": 0.0, "error": "finnhub unavailable or no key"}
    return raw
