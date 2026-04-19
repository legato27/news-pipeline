"""Finnhub news client.

Extracted from polymarket-agent/sentiment/finnhub_client.py.
API key is a parameter (not read from env) so the lib has no implicit config.
Shim modules in each app pull the key from their own settings/env layer.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

import httpx


logger = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"


def fetch_general_news(
    category: str = "general",
    *,
    api_key: str,
    min_id: int = 0,
    limit: int = 30,
    timeout: float = 15.0,
) -> list[dict]:
    """Fetch general news from Finnhub.

    Categories: general, forex, crypto, merger
    """
    if not api_key:
        logger.debug("finnhub_no_key category=%s", category)
        return []

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                f"{FINNHUB_BASE}/news",
                params={"category": category, "minId": min_id, "token": api_key},
            )
            resp.raise_for_status()
            raw = resp.json()

        articles: list[dict] = []
        for item in raw[:limit]:
            title = item.get("headline", "")
            summary = item.get("summary", "")
            url = item.get("url", "")
            source = item.get("source", "finnhub")
            ts = item.get("datetime", 0)

            if not title:
                continue

            pub_dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
            content_hash = hashlib.md5(f"{title}{url}".encode()).hexdigest()

            articles.append({
                "title": title,
                "summary": summary[:500],
                "url": url,
                "source": f"finnhub_{source}",
                "published_at": pub_dt.isoformat(),
                "content_hash": content_hash,
                "text": f"{title}. {summary[:300]}",
                "finnhub_id": item.get("id"),
                "related_tickers": item.get("related", "").split(",") if item.get("related") else [],
                "category": item.get("category", category),
            })

        logger.info("finnhub_fetched category=%s count=%d", category, len(articles))
        return articles

    except Exception as e:
        logger.warning("finnhub_error err=%s", e)
        return []


def fetch_company_news(
    symbol: str,
    *,
    api_key: str,
    days_back: int = 7,
    limit: int = 20,
    timeout: float = 15.0,
) -> list[dict]:
    """Fetch news for a specific company/ticker."""
    if not api_key:
        return []

    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days_back)

        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                f"{FINNHUB_BASE}/company-news",
                params={
                    "symbol": symbol,
                    "from": start.strftime("%Y-%m-%d"),
                    "to": end.strftime("%Y-%m-%d"),
                    "token": api_key,
                },
            )
            resp.raise_for_status()
            raw = resp.json()

        articles: list[dict] = []
        for item in raw[:limit]:
            title = item.get("headline", "")
            if not title:
                continue

            ts = item.get("datetime", 0)
            pub_dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
            url = item.get("url", "")

            articles.append({
                "title": title,
                "summary": item.get("summary", "")[:500],
                "url": url,
                "source": f"finnhub_{item.get('source', '')}",
                "published_at": pub_dt.isoformat(),
                "content_hash": hashlib.md5(f"{title}{url}".encode()).hexdigest(),
                "text": f"{title}. {item.get('summary', '')[:300]}",
                "ticker": symbol,
            })

        return articles

    except Exception as e:
        logger.warning("finnhub_company_error symbol=%s err=%s", symbol, e)
        return []


def fetch_market_sentiment(
    symbol: str = "SPY",
    *,
    api_key: str,
    timeout: float = 15.0,
) -> dict | None:
    """Fetch social sentiment from Finnhub (Reddit + Twitter buzz)."""
    if not api_key:
        return None

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                f"{FINNHUB_BASE}/stock/social-sentiment",
                params={"symbol": symbol, "token": api_key},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning("finnhub_sentiment_error err=%s", e)
        return None
