"""Reddit public JSON scraper (no auth).

Extracted from polymarket-agent/sentiment/reddit_scraper.py. Useful when PRAW credentials
are not configured. Rate-limited and brittle against Reddit's bot detection, so
`social/reddit_praw.py` is preferred when credentials are available.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from datetime import datetime, timezone

import httpx


logger = logging.getLogger(__name__)

SUBREDDITS: dict[str, dict] = {
    "stocks": {"category": "general", "weight": 1.0},
    "wallstreetbets": {"category": "general", "weight": 0.8},
    "cryptocurrency": {"category": "crypto", "weight": 1.0},
    "bitcoin": {"category": "crypto", "weight": 0.9},
    "investing": {"category": "general", "weight": 1.0},
    "economics": {"category": "macro", "weight": 0.9},
}

TICKER_PATTERN = re.compile(r'\b([A-Z]{1,5})\b')

TICKER_BLACKLIST: set[str] = {
    "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HER",
    "WAS", "ONE", "OUR", "OUT", "HAS", "HIS", "HOW", "ITS", "MAY", "NEW",
    "NOW", "OLD", "SEE", "WAY", "WHO", "DID", "GET", "HIM", "LET",
    "SAY", "SHE", "TOO", "USE", "ANY", "BIG", "FEW", "GOT", "HAD", "IMO",
    "CEO", "IPO", "ETF", "GDP", "CPI", "FED", "SEC", "FBI", "USA", "USD",
    "EUR", "GBP", "JPY", "API", "ATH", "DCA", "HODL", "FOMO", "FUD",
}


def fetch_subreddit_posts(
    subreddit: str,
    *,
    sort: str = "hot",
    limit: int = 25,
    user_agent: str = "NewsPipeline/1.0 (Financial Research)",
    timeout: float = 15.0,
) -> list[dict]:
    """Fetch posts from a subreddit using the public JSON endpoint."""
    try:
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
        resp = httpx.get(
            url,
            params={"limit": limit},
            headers={"User-Agent": user_agent},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        posts: list[dict] = []
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            title = post.get("title", "")
            selftext = post.get("selftext", "")[:500]
            score = post.get("score", 0)
            num_comments = post.get("num_comments", 0)
            created_utc = post.get("created_utc", 0)

            if not title:
                continue

            pub_dt = (
                datetime.fromtimestamp(created_utc, tz=timezone.utc)
                if created_utc
                else datetime.now(timezone.utc)
            )
            content_hash = hashlib.md5(f"reddit_{post.get('id', '')}".encode()).hexdigest()

            text = f"{title} {selftext}"
            tickers = _extract_tickers(text)

            posts.append({
                "title": title,
                "summary": selftext[:300],
                "text": f"{title}. {selftext[:200]}",
                "url": f"https://reddit.com{post.get('permalink', '')}",
                "source": f"reddit_r/{subreddit}",
                "published_at": pub_dt.isoformat(),
                "content_hash": content_hash,
                "score": score,
                "num_comments": num_comments,
                "tickers_mentioned": tickers,
                "subreddit": subreddit,
                "buzz_score": _calculate_buzz(score, num_comments),
            })

        return posts

    except Exception as e:
        logger.warning("reddit_public_fetch_error subreddit=%s err=%s", subreddit, e)
        return []


def crawl_all_subreddits(
    limit_per_sub: int = 15,
    subreddits: dict | None = None,
) -> list[dict]:
    """Crawl all configured subreddits, dedup by content_hash, sort by buzz."""
    if subreddits is None:
        subreddits = SUBREDDITS

    all_posts: list[dict] = []
    seen: set[str] = set()

    for subreddit in subreddits:
        posts = fetch_subreddit_posts(subreddit, limit=limit_per_sub)
        for post in posts:
            h = post["content_hash"]
            if h not in seen:
                seen.add(h)
                all_posts.append(post)

    all_posts.sort(key=lambda p: p.get("buzz_score", 0), reverse=True)
    logger.info(
        "reddit_public_crawl_complete subreddits=%d posts=%d",
        len(subreddits),
        len(all_posts),
    )
    return all_posts


def get_ticker_buzz(ticker: str, subreddits: dict | None = None) -> dict:
    """Get buzz score for a specific ticker across all subreddits."""
    if subreddits is None:
        subreddits = SUBREDDITS

    mentions = 0
    total_score = 0
    total_comments = 0
    posts: list[dict] = []

    for subreddit in subreddits:
        sub_posts = fetch_subreddit_posts(subreddit, sort="new", limit=50)
        for post in sub_posts:
            if ticker in post.get("tickers_mentioned", []):
                mentions += 1
                total_score += post.get("score", 0)
                total_comments += post.get("num_comments", 0)
                posts.append(post)

    return {
        "ticker": ticker,
        "mentions": mentions,
        "total_upvotes": total_score,
        "total_comments": total_comments,
        "buzz_score": _calculate_buzz(total_score, total_comments) * mentions,
        "top_posts": sorted(posts, key=lambda p: p["buzz_score"], reverse=True)[:5],
    }


def _extract_tickers(text: str) -> list[str]:
    """Extract potential stock tickers from text."""
    matches = TICKER_PATTERN.findall(text)
    tickers = [m for m in matches if m not in TICKER_BLACKLIST and len(m) >= 2]
    return list(set(tickers))[:10]


def _calculate_buzz(score: int, num_comments: int) -> float:
    """Buzz = log(1 + |score|) * log(1 + num_comments)."""
    return math.log1p(abs(score)) * math.log1p(num_comments)
