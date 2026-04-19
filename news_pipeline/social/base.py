"""SocialProvider protocol.

Phase 1: defines the interface. Phase 5 OSINT adds providers (Telegram, Bluesky, Mastodon)
that implement this protocol so they plug into the same aggregation pipeline.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SocialProvider(Protocol):
    """A source of social/forum posts keyed by ticker or free-text query.

    Implementations: finnhub_social, reddit_praw, reddit_public, stocktwits,
    and (Phase 5) telegram, bluesky, mastodon.
    """

    name: str

    def fetch_posts(self, query: str, *, limit: int = 50) -> list[dict]:
        """Return posts matching `query`. Shape: SocialPost-compatible dicts."""
        ...

    def fetch_ticker(self, ticker: str, *, limit: int = 50) -> list[dict]:
        """Return posts mentioning `ticker`. Default fallback: delegate to fetch_posts."""
        ...
