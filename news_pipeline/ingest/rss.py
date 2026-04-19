"""RSS feed crawler — financial + (Phase 5) geopolitical/OSINT.

Unified parser that subsumes both apps' implementations:
  - polymarket-agent/sentiment/rss_crawler.py (12 feeds, per_feed_limit=20, no language filter)
  - Project-StockPrediction/.../services/sentiment/rss_crawler.py (17 feeds, per_feed_limit=25,
    is_english filter, follow_redirects=True)

Both legacy behaviors are selectable via parameters so shim modules can preserve existing app behavior.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import httpx


logger = logging.getLogger(__name__)


# ── Polymarket legacy feed set (12) ─────────────────────────────────────────
RSS_FEEDS_POLYMARKET: dict[str, str] = {
    "reuters_markets": "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best",
    "reuters_business": "https://www.reutersagency.com/feed/?best-types=wire&post_type=best",
    "cnbc_top": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "cnbc_world": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362",
    "cnbc_finance": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
    "marketwatch_top": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "marketwatch_markets": "https://feeds.marketwatch.com/marketwatch/marketpulse/",
    "ap_business": "https://rsshub.app/apnews/topics/business",
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
    "investing_news": "https://www.investing.com/rss/news.rss",
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
}

# ── StockPrediction legacy feed set (17) ────────────────────────────────────
RSS_FEEDS_STOCKPREDICTION: dict[str, str] = {
    # --- Stocks & Markets ---
    "reuters_markets": "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best",
    "cnbc_finance": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
    "cnbc_investing": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
    "marketwatch_top": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "marketwatch_markets": "https://feeds.marketwatch.com/marketwatch/marketpulse/",
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
    "investing_news": "https://www.investing.com/rss/news.rss",
    "seekingalpha": "https://seekingalpha.com/market_currents.xml",
    # --- Crypto ---
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "theblock": "https://www.theblock.co/rss.xml",
    "decrypt": "https://decrypt.co/feed",
    "cryptoslate": "https://cryptoslate.com/feed/",
    "newsbtc": "https://www.newsbtc.com/feed/",
    "dailyhodl": "https://dailyhodl.com/feed/",
    "ambcrypto": "https://ambcrypto.com/feed/",
    "blockonomi": "https://blockonomi.com/feed/",
    "bitcoinist": "https://bitcoinist.com/feed/",
}

# ── Unified financial feed set (union, dedup'd by URL) ──────────────────────
RSS_FEEDS_FINANCIAL: dict[str, str] = {**RSS_FEEDS_POLYMARKET, **RSS_FEEDS_STOCKPREDICTION}

# Category-specific subsets (polymarket legacy API)
RSS_FEEDS_BY_CATEGORY: dict[str, dict[str, str]] = {
    "crude_oil": {
        "reuters_markets": RSS_FEEDS_POLYMARKET["reuters_markets"],
        "marketwatch_markets": RSS_FEEDS_POLYMARKET["marketwatch_markets"],
        "investing_news": RSS_FEEDS_POLYMARKET["investing_news"],
    },
    "btc_milestones": {
        "coindesk": RSS_FEEDS_POLYMARKET["coindesk"],
        "cointelegraph": RSS_FEEDS_POLYMARKET["cointelegraph"],
        "cnbc_finance": RSS_FEEDS_POLYMARKET["cnbc_finance"],
    },
    "fed_decisions": {
        "reuters_markets": RSS_FEEDS_POLYMARKET["reuters_markets"],
        "cnbc_finance": RSS_FEEDS_POLYMARKET["cnbc_finance"],
        "marketwatch_top": RSS_FEEDS_POLYMARKET["marketwatch_top"],
    },
    "ai_predictions": {
        "reuters_business": RSS_FEEDS_POLYMARKET["reuters_business"],
        "cnbc_top": RSS_FEEDS_POLYMARKET["cnbc_top"],
    },
}


def _parse_feed(
    feed_url: str,
    source_name: str,
    *,
    per_feed_limit: int = 25,
    filter_english: bool = False,
    user_agent: str = "NewsPipeline/1.0 (+https://fin.vibelife.sg)",
    follow_redirects: bool = True,
    timeout: float = 15.0,
) -> list[dict]:
    """Parse a single RSS feed and return article dicts compatible with both apps' consumers."""
    try:
        import feedparser
    except ImportError:
        logger.error("feedparser not installed: pip install feedparser")
        return []

    try:
        resp = httpx.get(
            feed_url,
            timeout=timeout,
            headers={"User-Agent": user_agent},
            follow_redirects=follow_redirects,
        )
        if resp.status_code != 200:
            return []

        feed = feedparser.parse(resp.text)
        articles: list[dict] = []

        for entry in feed.entries[:per_feed_limit]:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            link = entry.get("link", "")

            if not title:
                continue

            if filter_english:
                from news_pipeline.matching.lang import is_english
                if not is_english(f"{title} {summary}"):
                    continue

            try:
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                else:
                    pub_dt = datetime.now(timezone.utc)
            except Exception:
                pub_dt = datetime.now(timezone.utc)

            content_hash = hashlib.md5(f"{title}{link}".encode()).hexdigest()

            articles.append({
                "title": title,
                "summary": summary[:500],
                "url": link,
                "source": source_name,
                "published_at": pub_dt.isoformat(),
                "content_hash": content_hash,
                "text": f"{title}. {summary[:300]}",
            })

        return articles

    except Exception as e:
        logger.warning("rss_parse_error source=%s err=%s", source_name, e)
        return []


def crawl_all_feeds(
    feeds: dict[str, str] | None = None,
    *,
    per_feed_limit: int = 25,
    filter_english: bool = False,
    user_agent: str = "NewsPipeline/1.0 (+https://fin.vibelife.sg)",
    follow_redirects: bool = True,
) -> list[dict]:
    """Crawl all configured RSS feeds. Dedup by content_hash, sort by recency.

    Default feed set is the unified financial superset. Shim modules can pass
    their legacy feed dict to preserve per-app behavior.
    """
    if feeds is None:
        feeds = RSS_FEEDS_FINANCIAL

    all_articles: list[dict] = []
    seen: set[str] = set()

    for source_name, feed_url in feeds.items():
        articles = _parse_feed(
            feed_url,
            source_name,
            per_feed_limit=per_feed_limit,
            filter_english=filter_english,
            user_agent=user_agent,
            follow_redirects=follow_redirects,
        )
        for article in articles:
            h = article["content_hash"]
            if h not in seen:
                seen.add(h)
                all_articles.append(article)

    all_articles.sort(key=lambda a: a.get("published_at", ""), reverse=True)
    logger.info("rss_crawl_complete sources=%d articles=%d", len(feeds), len(all_articles))
    return all_articles


def crawl_category_feeds(category: str, **kwargs) -> list[dict]:
    """Crawl feeds relevant to a polymarket market category."""
    feeds = RSS_FEEDS_BY_CATEGORY.get(category, RSS_FEEDS_POLYMARKET)
    return crawl_all_feeds(feeds, **kwargs)
