"""Canonical schemas for news + sentiment.

Union of the ad-hoc dict shapes used by polymarket-agent and Project-StockPrediction.
Pydantic v2 so both FastAPI apps can serialize these directly.

Phase 5 will add OsintEvent, Actor, GeoLocation here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SourceKind = Literal[
    "rss",
    "newsapi",
    "finnhub",
    "reddit",
    "stocktwits",
    # Reserved for Phase 5+
    "telegram",
    "bluesky",
    "mastodon",
    "gdelt",
    "acled",
    "reliefweb",
    "cisa",
    "misp",
    "otx",
    "sanctions",
    "osint_rss",
]


class SentimentScore(BaseModel):
    """Standardized sentiment output from any scorer (VADER, FinBERT, LLM, composite)."""

    model_config = ConfigDict(extra="allow")

    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    model: str
    label: Literal["positive", "negative", "neutral"]
    elapsed_ms: float = 0.0


class RedditMeta(BaseModel):
    """Reddit-specific metadata attached to an Article or SocialPost."""

    subreddit: str
    score: int = 0
    num_comments: int = 0
    buzz_score: float = 0.0


class Article(BaseModel):
    """Canonical news article. Supersedes both apps' ad-hoc dicts.

    `content_hash` is the authoritative dedup key (md5(title + url)).
    `url` is the secondary dedup key used by StockPrediction's sentiment_cache.source_url.
    """

    model_config = ConfigDict(extra="allow")

    content_hash: str
    title: str
    summary: str | None = None
    text: str = ""
    url: str = ""
    source: str
    source_kind: SourceKind = "rss"
    published_at: datetime | str | None = None
    language: str = "en"
    original_language: str | None = None
    translated_text: str | None = None
    tickers_mentioned: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)

    # Source-kind-specific extras (kept flat for back-compat with existing dict consumers)
    finnhub_id: int | None = None
    related_tickers: list[str] = Field(default_factory=list)
    reddit: RedditMeta | None = None

    # Filled after scoring
    sentiment: SentimentScore | dict | None = None

    # Passthrough for feed-specific fields (GDELT cols, etc.) — used in later phases
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Article":
        """Construct from either polymarket-style or StockPrediction-style dicts.

        Both currently use flat dicts with overlapping keys. Unknown keys land in
        `raw` via model_validate's extra="allow", but we keep core fields explicit.
        """
        return cls.model_validate(data)


class SocialPost(BaseModel):
    """Social/forum post (Reddit, StockTwits, Telegram, Bluesky, etc.).

    Shares `content_hash`, `source_kind`, `sentiment` with Article so downstream
    aggregation can treat them uniformly.
    """

    model_config = ConfigDict(extra="allow")

    content_hash: str
    title: str = ""
    text: str = ""
    url: str = ""
    source: str
    source_kind: SourceKind
    published_at: datetime | str | None = None
    author: str | None = None
    tickers_mentioned: list[str] = Field(default_factory=list)
    reddit: RedditMeta | None = None
    buzz_score: float = 0.0
    sentiment: SentimentScore | dict | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
