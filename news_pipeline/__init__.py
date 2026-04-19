"""news-pipeline: shared news/sentiment ingest, matching, scoring.

Consumed by polymarket-agent and Project-StockPrediction.
"""
from news_pipeline.schema import (
    Article,
    SentimentScore,
    SocialPost,
    RedditMeta,
)

__version__ = "0.1.0"

__all__ = ["Article", "SentimentScore", "SocialPost", "RedditMeta", "__version__"]
