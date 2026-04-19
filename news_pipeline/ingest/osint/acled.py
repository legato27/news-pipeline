"""ACLED (Armed Conflict Location & Event Data) ingest.

Requires ACLED API access — set env vars:
  ACLED_API_KEY, ACLED_EMAIL

API docs: https://apidocs.acleddata.com/

The query below pulls events from the last 7 days, ordered by event_date desc.
"""
from __future__ import annotations

import hashlib
import logging
import os

import httpx


logger = logging.getLogger(__name__)

BASE_URL = "https://api.acleddata.com/acled/read"


def fetch_recent(*, limit: int = 500, days_back: int = 7, timeout: float = 30.0) -> list[dict]:
    """Fetch recent ACLED events. Returns empty list if credentials missing."""
    api_key = os.getenv("ACLED_API_KEY", "")
    email = os.getenv("ACLED_EMAIL", "")
    if not api_key or not email:
        logger.debug("acled_credentials_missing")
        return []

    try:
        with httpx.Client(timeout=timeout) as c:
            resp = c.get(
                BASE_URL,
                params={
                    "key": api_key,
                    "email": email,
                    "limit": limit,
                    "event_date": f"{days_back}|0",
                    "event_date_where": "BETWEEN",
                    "terms": "accept",
                },
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
    except Exception as e:
        logger.warning("acled_fetch_failed err=%s", e)
        return []

    articles: list[dict] = []
    for item in data:
        event_id = item.get("data_id", "")
        event_date = item.get("event_date", "")
        notes = item.get("notes", "").strip()
        event_type = item.get("event_type", "")
        sub_event = item.get("sub_event_type", "")
        country = item.get("country", "")
        location = item.get("location", "")
        actor1 = item.get("actor1", "")
        actor2 = item.get("actor2", "")
        fatalities = item.get("fatalities", 0)
        source = item.get("source", "")

        title = f"[{event_type}] {actor1} vs {actor2} — {location}, {country}".strip(" —")
        content_hash = hashlib.md5(f"acled_{event_id}".encode()).hexdigest()

        articles.append({
            "content_hash": content_hash,
            "title": title[:500],
            "summary": notes[:500],
            "text": f"{title}. {notes[:300]}",
            "url": item.get("source_scale_url") or f"https://acleddata.com/#/dashboard?event={event_id}",
            "source": f"acled_{source.lower().replace(' ', '_')}" if source else "acled",
            "source_kind": "acled",
            "published_at": f"{event_date}T00:00:00+00:00" if event_date else None,
            "language": "en",
            "raw": {
                "event_type": event_type,
                "sub_event_type": sub_event,
                "country": country,
                "location": location,
                "lat": item.get("latitude"),
                "lon": item.get("longitude"),
                "actor1": actor1,
                "actor2": actor2,
                "fatalities": fatalities,
            },
        })

    logger.info("acled_crawl_complete events=%d", len(articles))
    return articles
