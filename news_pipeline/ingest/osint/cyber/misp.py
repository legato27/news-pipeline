"""MISP (Malware Information Sharing Platform) feed puller.

MISP instances are self-hosted; this module pulls events from a configured
instance URL + API key. Set env vars:
  MISP_BASE_URL (e.g., https://misp.your-org.example/)
  MISP_API_KEY

API: GET /events/restSearch (JSON) with filters last=7d etc.
"""
from __future__ import annotations

import hashlib
import logging
import os

import httpx


logger = logging.getLogger(__name__)


def fetch_recent(*, last: str = "7d", limit: int = 100, timeout: float = 30.0) -> list[dict]:
    base_url = os.getenv("MISP_BASE_URL", "").rstrip("/")
    api_key = os.getenv("MISP_API_KEY", "")
    if not base_url or not api_key:
        logger.debug("misp_config_missing")
        return []

    try:
        with httpx.Client(timeout=timeout, verify=False) as c:
            resp = c.post(
                f"{base_url}/events/restSearch",
                json={"returnFormat": "json", "last": last, "limit": limit},
                headers={
                    "Authorization": api_key,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        logger.warning("misp_fetch_failed err=%s", e)
        return []

    articles: list[dict] = []
    for entry in payload.get("response", []):
        event = entry.get("Event", {}) if isinstance(entry, dict) else {}
        event_id = event.get("id", "")
        info = event.get("info", "")
        if not info:
            continue

        threat_level = event.get("threat_level_id")
        attribute_count = len(event.get("Attribute", []))
        url = f"{base_url}/events/view/{event_id}"
        content_hash = hashlib.md5(f"misp_{event_id}_{base_url}".encode()).hexdigest()

        articles.append({
            "content_hash": content_hash,
            "title": f"[MISP] {info}"[:500],
            "summary": info[:500],
            "text": info,
            "url": url,
            "source": "misp",
            "source_kind": "misp",
            "published_at": event.get("date"),
            "language": "en",
            "raw": {
                "event_id": event_id,
                "threat_level_id": threat_level,
                "analysis": event.get("analysis"),
                "attribute_count": attribute_count,
                "orgc": event.get("Orgc", {}).get("name"),
            },
        })

    logger.info("misp_crawl_complete events=%d", len(articles))
    return articles
