"""NewsAPI client.

Extracted from Project-StockPrediction/.../services/sentiment/news_sentiment._fetch_news.
API key is a parameter, not read from env.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx


logger = logging.getLogger(__name__)

NEWSAPI_BASE = "https://newsapi.org/v2"


async def fetch_articles(
    query: str,
    *,
    api_key: str,
    page_size: int = 20,
    days_back: int = 7,
    language: str = "en",
    sort_by: str = "publishedAt",
    timeout: float = 15.0,
) -> list[dict]:
    """Fetch articles from NewsAPI /everything. Returns the raw article dicts
    from NewsAPI (with keys like title, description, url, publishedAt, source).
    Callers are responsible for normalizing to Article schema.
    """
    if not api_key:
        return []

    try:
        from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
        params = {
            "q": query,
            "apiKey": api_key,
            "language": language,
            "sortBy": sort_by,
            "pageSize": page_size,
            "from": from_date,
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{NEWSAPI_BASE}/everything", params=params)
            resp.raise_for_status()
            return resp.json().get("articles", [])
    except Exception as e:
        logger.error("newsapi_fetch_failed err=%s", e)
        return []
