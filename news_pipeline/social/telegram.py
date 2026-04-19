"""Telegram public-channel scraper.

Two implementation paths:
  1. t.me web scrape (no auth, brittle, rate-limited) — used by default
  2. MTProto via Telethon (requires TELEGRAM_API_ID + TELEGRAM_API_HASH) — TODO

For Phase 5 we implement (1). A configured list of public channel usernames is
scraped from t.me/s/{channel} which exposes the last ~20 posts as HTML.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone

import httpx


logger = logging.getLogger(__name__)


# Default OSINT-relevant channels. Override via env TELEGRAM_CHANNELS (comma-separated).
DEFAULT_CHANNELS: list[str] = [
    # Conflict OSINT
    "intelslava",
    "ukraine_watch",
    "DeepStateUA",
    # Cyber
    "cybersecuritynews",
    # Financial / crypto
    "cointelegraph",
    "whalealert_io",
]


def _scrape_channel(channel: str, *, timeout: float = 15.0) -> list[dict]:
    """Scrape t.me/s/{channel} and extract recent posts."""
    url = f"https://t.me/s/{channel}"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            resp = c.get(url, headers={"User-Agent": "NewsPipeline-OSINT/1.0"})
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.warning("telegram_scrape_failed channel=%s err=%s", channel, e)
        return []

    # Extract post blocks. t.me/s embeds each message in a div with class
    # 'tgme_widget_message' and attributes data-post="channel/N".
    posts: list[dict] = []
    post_blocks = re.findall(
        r'data-post="([^"]+)"[^>]*>.*?<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
        html,
        re.DOTALL,
    )
    dates = re.findall(r'<time[^>]*datetime="([^"]+)"', html)

    for (post_id, body), dt in zip(post_blocks, dates):
        text = re.sub(r"<[^>]+>", " ", body).strip()
        text = re.sub(r"\s+", " ", text)
        if not text:
            continue
        content_hash = hashlib.md5(f"telegram_{post_id}".encode()).hexdigest()
        posts.append({
            "content_hash": content_hash,
            "title": text[:200],
            "text": text[:2000],
            "summary": text[:500],
            "url": f"https://t.me/{post_id}",
            "source": f"telegram_{channel}",
            "source_kind": "telegram",
            "published_at": dt,
            "language": "auto",
            "raw": {"channel": channel, "post_id": post_id},
        })

    return posts


def fetch_recent(*, channels: list[str] | None = None) -> list[dict]:
    channels = channels or DEFAULT_CHANNELS
    all_posts: list[dict] = []
    seen: set[str] = set()

    for ch in channels:
        for p in _scrape_channel(ch):
            if p["content_hash"] in seen:
                continue
            seen.add(p["content_hash"])
            all_posts.append(p)

    logger.info("telegram_crawl_complete channels=%d posts=%d", len(channels), len(all_posts))
    return all_posts
