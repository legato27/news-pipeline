"""CISA ingest — Known Exploited Vulnerabilities catalog + advisories.

Public JSON feeds:
  https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
  https://www.cisa.gov/cybersecurity-advisories/all.xml
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import httpx

from news_pipeline.ingest.rss import _parse_feed


logger = logging.getLogger(__name__)

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
ADVISORIES_RSS = "https://www.cisa.gov/cybersecurity-advisories/all.xml"


def fetch_kev(*, timeout: float = 30.0, limit: int = 200) -> list[dict]:
    """Fetch the CISA Known Exploited Vulnerabilities catalog.

    Returns the latest `limit` entries by dateAdded desc.
    """
    try:
        with httpx.Client(timeout=timeout) as c:
            resp = c.get(KEV_URL)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        logger.warning("cisa_kev_fetch_failed err=%s", e)
        return []

    vulns = payload.get("vulnerabilities", [])
    vulns.sort(key=lambda v: v.get("dateAdded", ""), reverse=True)

    articles: list[dict] = []
    for v in vulns[:limit]:
        cve = v.get("cveID", "")
        if not cve:
            continue

        title = f"[KEV {cve}] {v.get('vulnerabilityName', '')}".strip()
        summary = v.get("shortDescription", "")
        date_added = v.get("dateAdded")
        url = f"https://nvd.nist.gov/vuln/detail/{cve}"
        content_hash = hashlib.md5(f"cisa_kev_{cve}".encode()).hexdigest()

        pub_dt = None
        if date_added:
            try:
                pub_dt = datetime.fromisoformat(date_added).replace(tzinfo=timezone.utc).isoformat()
            except Exception:
                pass

        articles.append({
            "content_hash": content_hash,
            "title": title[:500],
            "summary": summary[:500],
            "text": f"{title}. {summary[:300]}",
            "url": url,
            "source": "cisa_kev",
            "source_kind": "cisa",
            "published_at": pub_dt,
            "language": "en",
            "raw": {
                "cve_id": cve,
                "vendor": v.get("vendorProject"),
                "product": v.get("product"),
                "required_action": v.get("requiredAction"),
                "due_date": v.get("dueDate"),
                "known_ransomware": v.get("knownRansomwareCampaignUse"),
            },
        })
    return articles


def fetch_advisories(*, per_feed_limit: int = 50) -> list[dict]:
    """Fetch CISA cybersecurity advisories via the RSS feed."""
    articles = _parse_feed(
        ADVISORIES_RSS,
        "cisa_advisories",
        per_feed_limit=per_feed_limit,
        user_agent="NewsPipeline-OSINT/1.0",
        follow_redirects=True,
    )
    for a in articles:
        a["source_kind"] = "cisa"
    return articles


def fetch_recent() -> list[dict]:
    """Combined CISA feed: KEV + advisories."""
    articles = fetch_kev() + fetch_advisories()
    logger.info("cisa_crawl_complete articles=%d", len(articles))
    return articles
