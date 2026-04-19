"""Reddit sentiment via PRAW (authenticated).

Extracted from Project-StockPrediction/.../services/sentiment/reddit_sentiment.py.
Credentials are parameters — caller reads them from its own settings layer.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from news_pipeline.scoring.vader import score_vader_compound


logger = logging.getLogger(__name__)

DEFAULT_SUBREDDITS: list[str] = ["stocks", "investing", "SecurityAnalysis", "wallstreetbets"]


def _get_reddit_client(client_id: str, client_secret: str, user_agent: str):
    import praw
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )


def _mentions_ticker(text: str, ticker: str) -> bool:
    return bool(re.search(rf"\b{re.escape(ticker)}\b", text, re.IGNORECASE))


def fetch_ticker_sentiment(
    ticker: str,
    *,
    client_id: str,
    client_secret: str,
    user_agent: str,
    subreddits: list[str] | None = None,
    post_limit: int = 100,
) -> dict:
    """Fetch Reddit posts mentioning `ticker` and compute VADER sentiment.

    Synchronous; caller is responsible for asyncio.to_thread wrapping if needed.
    """
    ticker = ticker.upper()
    if subreddits is None:
        subreddits = DEFAULT_SUBREDDITS

    if not client_id:
        return {"ticker": ticker, "score": 0.0, "error": "Reddit API not configured"}

    try:
        reddit = _get_reddit_client(client_id, client_secret, user_agent)
    except Exception as e:
        logger.error("reddit_praw_client_error err=%s", e)
        return {"ticker": ticker, "score": 0.0, "error": str(e)}

    scores: list[tuple[float, int]] = []
    posts_found = 0

    for subreddit_name in subreddits:
        try:
            subreddit = reddit.subreddit(subreddit_name)
            for post in subreddit.search(ticker, sort="new", time_filter="week", limit=post_limit):
                title = post.title or ""
                body = post.selftext or ""
                full_text = f"{title} {body}"

                if not _mentions_ticker(full_text, ticker):
                    continue

                score = score_vader_compound(full_text)
                weight = max(1, post.score)
                scores.append((score, weight))
                posts_found += 1
        except Exception as e:
            logger.debug("reddit_praw_subreddit_error sub=%s err=%s", subreddit_name, e)

    if not scores:
        return {"ticker": ticker, "score": 0.0, "posts_found": 0}

    total_weight = sum(w for _, w in scores)
    weighted_score = sum(s * w for s, w in scores) / total_weight

    positive = sum(1 for s, _ in scores if s > 0.05)
    negative = sum(1 for s, _ in scores if s < -0.05)

    return {
        "ticker": ticker,
        "score": round(float(weighted_score), 4),
        "posts_found": posts_found,
        "positive_posts": positive,
        "negative_posts": negative,
        "neutral_posts": posts_found - positive - negative,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
