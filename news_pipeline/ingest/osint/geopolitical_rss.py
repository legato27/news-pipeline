"""Geopolitical RSS feeds — conflict, diplomacy, think-tank analysis.

Distinct from the financial RSS set in ingest/rss.py. Same parser under the hood.
"""
from __future__ import annotations

import logging

from news_pipeline.ingest.rss import _parse_feed


logger = logging.getLogger(__name__)


GEOPOLITICAL_RSS_FEEDS: dict[str, str] = {
    # ── Wire / world desks ───────────────────────────────────────
    "reuters_world": "https://www.reutersagency.com/feed/?best-topics=world&post_type=best",
    "ap_world": "https://rsshub.app/apnews/topics/world-news",
    "bbc_world": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "aljazeera_world": "https://www.aljazeera.com/xml/rss/all.xml",
    "dw_world": "https://rss.dw.com/xml/rss-en-all",
    "xinhua_world": "http://www.xinhuanet.com/english/rss/worldrss.xml",
    "kyodo_world": "https://english.kyodonews.net/rss/news.xml",
    # ── Regional ─────────────────────────────────────────────────
    "scmp_asia": "https://www.scmp.com/rss/91/feed",
    "thehindu_world": "https://www.thehindu.com/news/international/feeder/default.rss",
    "elpais_english": "https://feeds.elpais.com/mrss-s/pages/ep/site/english.elpais.com/portada",
    "mercopress_latam": "https://en.mercopress.com/rss",
    # ── Think tanks / analysis ──────────────────────────────────
    "isw_analysis": "https://www.understandingwar.org/rss.xml",
    "csis_analysis": "https://www.csis.org/analysis/feed",
    "chathamhouse": "https://www.chathamhouse.org/rss/all",
    "rand_analysis": "https://www.rand.org/pubs.xml",
    "cfr_articles": "https://www.cfr.org/articles/rss.xml",
    "brookings_foreign_policy": "https://www.brookings.edu/topic/foreign-policy/feed/",
    # ── Defense / security press ────────────────────────────────
    "defense_one": "https://www.defenseone.com/rss/all/",
    "warontherocks": "https://warontherocks.com/feed/",
    "janes_news": "https://www.janes.com/feeds/news",
    # ── Policy / intelligence ───────────────────────────────────
    "foreignpolicy": "https://foreignpolicy.com/feed/",
    "foreignaffairs": "https://www.foreignaffairs.com/rss.xml",
    "lawfareblog": "https://www.lawfareblog.com/rss.xml",
    # ── UN / humanitarian ───────────────────────────────────────
    "un_news": "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
}


def fetch_recent(*, per_feed_limit: int = 25) -> list[dict]:
    """Fetch latest articles from all geopolitical RSS feeds.

    Returns Article-compatible dicts with source_kind='osint_rss'.
    """
    all_articles: list[dict] = []
    seen: set[str] = set()

    for source_name, url in GEOPOLITICAL_RSS_FEEDS.items():
        for article in _parse_feed(
            url,
            source_name,
            per_feed_limit=per_feed_limit,
            filter_english=False,  # OSINT keeps non-English; translation in Phase 6
            user_agent="NewsPipeline-OSINT/1.0",
            follow_redirects=True,
        ):
            h = article["content_hash"]
            if h in seen:
                continue
            seen.add(h)
            article["source_kind"] = "osint_rss"
            all_articles.append(article)

    logger.info("geopolitical_rss_crawl_complete sources=%d articles=%d",
                len(GEOPOLITICAL_RSS_FEEDS), len(all_articles))
    return all_articles
