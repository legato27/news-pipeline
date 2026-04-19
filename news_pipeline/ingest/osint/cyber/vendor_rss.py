"""Cyber vendor threat-intel blog RSS feeds.

Mandiant, CrowdStrike, Unit 42, Cisco Talos, Microsoft MSRC, Google TAG.
"""
from __future__ import annotations

import logging

from news_pipeline.ingest.rss import _parse_feed


logger = logging.getLogger(__name__)


VENDOR_RSS_FEEDS: dict[str, str] = {
    "mandiant_blog": "https://www.mandiant.com/resources/blog/rss.xml",
    "crowdstrike_blog": "https://www.crowdstrike.com/blog/feed",
    "unit42": "https://unit42.paloaltonetworks.com/feed/",
    "talos_blog": "https://blog.talosintelligence.com/feeds/posts/default?alt=rss",
    "msrc_blog": "https://msrc.microsoft.com/blog/feed",
    "google_tag": "https://blog.google/threat-analysis-group/rss/",
    "sentinelone_labs": "https://www.sentinelone.com/labs/feed/",
    "sans_isc": "https://isc.sans.edu/rssfeed.xml",
}


def fetch_recent(*, per_feed_limit: int = 15) -> list[dict]:
    all_articles: list[dict] = []
    seen: set[str] = set()

    for source_name, url in VENDOR_RSS_FEEDS.items():
        for article in _parse_feed(
            url,
            source_name,
            per_feed_limit=per_feed_limit,
            user_agent="NewsPipeline-OSINT/1.0",
            follow_redirects=True,
        ):
            h = article["content_hash"]
            if h in seen:
                continue
            seen.add(h)
            article["source_kind"] = "osint_rss"
            all_articles.append(article)

    logger.info("cyber_vendor_rss_crawl_complete articles=%d", len(all_articles))
    return all_articles
