"""OCHA ReliefWeb ingest — humanitarian disasters, displacement, reports.

Public API (no key required):
  https://api.reliefweb.int/v1/reports?appname=news-pipeline&limit=50&sort[]=date:desc
"""
from __future__ import annotations

import hashlib
import logging

import httpx


logger = logging.getLogger(__name__)

BASE_URL = "https://api.reliefweb.int/v1"
APP_NAME = "news-pipeline"


def fetch_recent(*, limit: int = 100, timeout: float = 20.0) -> list[dict]:
    """Fetch latest ReliefWeb reports."""
    try:
        with httpx.Client(timeout=timeout) as c:
            resp = c.get(
                f"{BASE_URL}/reports",
                params={
                    "appname": APP_NAME,
                    "limit": limit,
                    "sort[]": "date:desc",
                    "profile": "full",
                },
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
    except Exception as e:
        logger.warning("reliefweb_fetch_failed err=%s", e)
        return []

    articles: list[dict] = []
    for item in data:
        fields = item.get("fields", {})
        title = fields.get("title", "").strip()
        url = fields.get("url", "")
        if not title or not url:
            continue

        summary = (fields.get("body-html") or fields.get("body") or "")[:500]
        published = fields.get("date", {}).get("original") or fields.get("date", {}).get("created")
        countries = [c.get("name", "") for c in fields.get("country", []) if c.get("name")]
        disaster_types = [d.get("name", "") for d in fields.get("disaster_type", []) if d.get("name")]

        content_hash = hashlib.md5(f"reliefweb_{item.get('id', '')}{url}".encode()).hexdigest()

        articles.append({
            "content_hash": content_hash,
            "title": title[:500],
            "summary": summary,
            "text": f"{title}. {summary[:300]}",
            "url": url,
            "source": "reliefweb",
            "source_kind": "reliefweb",
            "published_at": published,
            "language": "en",
            "raw": {
                "countries": countries,
                "disaster_types": disaster_types,
                "origin": fields.get("origin"),
            },
        })

    logger.info("reliefweb_crawl_complete articles=%d", len(articles))
    return articles
