"""SEC enforcement actions RSS feed.

Public RSS at https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=&company=&dateb=&owner=include&count=40&action=getcurrent
(too noisy). Use the SEC litigation RSS:
  https://www.sec.gov/rss/litigation/litreleases.xml
"""
from __future__ import annotations

import logging

from news_pipeline.ingest.rss import _parse_feed


logger = logging.getLogger(__name__)

SEC_LITIGATION_RSS = "https://www.sec.gov/rss/litigation/litreleases.xml"


def fetch_recent(*, per_feed_limit: int = 40) -> list[dict]:
    articles = _parse_feed(
        SEC_LITIGATION_RSS,
        "sec_litigation",
        per_feed_limit=per_feed_limit,
        user_agent="NewsPipeline-OSINT/1.0 legato@vibelife.sg",  # SEC requires contact in UA
        follow_redirects=True,
    )
    for a in articles:
        a["source_kind"] = "sanctions"
    logger.info("sec_enforcement_crawl_complete articles=%d", len(articles))
    return articles
