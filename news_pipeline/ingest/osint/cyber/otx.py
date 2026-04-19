"""AlienVault OTX pulses.

Requires OTX_API_KEY env var. Free tier available at https://otx.alienvault.com/
API: https://otx.alienvault.com/api/v1/pulses/subscribed?limit=50
"""
from __future__ import annotations

import hashlib
import logging
import os

import httpx


logger = logging.getLogger(__name__)

BASE_URL = "https://otx.alienvault.com/api/v1"


def fetch_recent(*, limit: int = 100, timeout: float = 30.0) -> list[dict]:
    api_key = os.getenv("OTX_API_KEY", "")
    if not api_key:
        logger.debug("otx_api_key_missing")
        return []

    try:
        with httpx.Client(timeout=timeout) as c:
            resp = c.get(
                f"{BASE_URL}/pulses/subscribed",
                params={"limit": limit},
                headers={"X-OTX-API-KEY": api_key},
            )
            resp.raise_for_status()
            pulses = resp.json().get("results", [])
    except Exception as e:
        logger.warning("otx_fetch_failed err=%s", e)
        return []

    articles: list[dict] = []
    for pulse in pulses:
        pulse_id = pulse.get("id", "")
        name = pulse.get("name", "")
        if not name:
            continue

        description = pulse.get("description", "")[:1000]
        tlp = pulse.get("TLP", "white")
        tags = pulse.get("tags", [])
        indicator_count = len(pulse.get("indicators", []))
        url = f"https://otx.alienvault.com/pulse/{pulse_id}"
        content_hash = hashlib.md5(f"otx_{pulse_id}".encode()).hexdigest()

        articles.append({
            "content_hash": content_hash,
            "title": f"[OTX] {name}"[:500],
            "summary": description[:500],
            "text": f"{name}. {description[:300]}",
            "url": url,
            "source": "otx_alienvault",
            "source_kind": "otx",
            "published_at": pulse.get("created"),
            "language": "en",
            "raw": {
                "tlp": tlp,
                "tags": tags,
                "indicator_count": indicator_count,
                "adversary": pulse.get("adversary"),
                "malware_families": pulse.get("malware_families", []),
                "industries": pulse.get("industries", []),
            },
        })

    logger.info("otx_crawl_complete pulses=%d", len(articles))
    return articles
