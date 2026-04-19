"""Bluesky (AT protocol) ingest.

Uses the public app.bsky.feed.searchPosts endpoint (no auth required) to pull
posts matching a keyword query. For Phase 5 we query a handful of OSINT-relevant
terms (configurable via BLUESKY_QUERIES env var).

Docs: https://docs.bsky.app/docs/api/app-bsky-feed-search-posts
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone

import httpx


logger = logging.getLogger(__name__)

SEARCH_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"

DEFAULT_QUERIES: list[str] = [
    "breaking",
    "sanctions",
    "cyberattack",
    "conflict",
]


def _search(query: str, *, limit: int = 50, timeout: float = 15.0) -> list[dict]:
    try:
        with httpx.Client(timeout=timeout) as c:
            resp = c.get(SEARCH_URL, params={"q": query, "limit": limit})
            resp.raise_for_status()
            return resp.json().get("posts", [])
    except Exception as e:
        logger.warning("bluesky_search_failed query=%s err=%s", query, e)
        return []


def fetch_recent(*, queries: list[str] | None = None) -> list[dict]:
    env_qs = os.getenv("BLUESKY_QUERIES", "")
    if env_qs:
        queries = [q.strip() for q in env_qs.split(",") if q.strip()]
    queries = queries or DEFAULT_QUERIES

    all_posts: list[dict] = []
    seen: set[str] = set()

    for q in queries:
        for post in _search(q):
            uri = post.get("uri", "")
            record = post.get("record", {})
            text = (record.get("text") or "").strip()
            if not text or not uri:
                continue

            author = post.get("author", {}).get("handle", "")
            created = record.get("createdAt") or datetime.now(timezone.utc).isoformat()
            content_hash = hashlib.md5(f"bluesky_{uri}".encode()).hexdigest()

            if content_hash in seen:
                continue
            seen.add(content_hash)

            # Build a usable https URL: https://bsky.app/profile/{handle}/post/{rkey}
            rkey = uri.split("/")[-1] if "/" in uri else ""
            url = f"https://bsky.app/profile/{author}/post/{rkey}" if author and rkey else uri

            all_posts.append({
                "content_hash": content_hash,
                "title": text[:200],
                "text": text[:2000],
                "summary": text[:500],
                "url": url,
                "source": f"bluesky_{author}" if author else "bluesky",
                "source_kind": "bluesky",
                "published_at": created,
                "language": record.get("langs", ["auto"])[0] if record.get("langs") else "auto",
                "raw": {
                    "uri": uri,
                    "query": q,
                    "like_count": post.get("likeCount", 0),
                    "repost_count": post.get("repostCount", 0),
                    "reply_count": post.get("replyCount", 0),
                },
            })

    logger.info("bluesky_crawl_complete posts=%d", len(all_posts))
    return all_posts
