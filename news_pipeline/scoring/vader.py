"""VADER scorer with finance-specific lexicon extensions.

Extracted from polymarket-agent/sentiment/nlp_pipeline.py:37-99. Runs on cloud
(CPU, <100 ms per call) — not worth a network hop to DGX.
"""
from __future__ import annotations

import logging
import time

from news_pipeline.schema import SentimentScore


logger = logging.getLogger(__name__)

_vader = None

FINANCE_LEXICON: dict[str, float] = {
    "bullish": 2.5, "bearish": -2.5, "rally": 2.0, "crash": -3.0,
    "surge": 2.0, "plunge": -2.5, "soar": 2.5, "tank": -2.5,
    "moon": 2.0, "dump": -2.0, "breakout": 1.5, "breakdown": -1.5,
    "upgrade": 1.5, "downgrade": -1.5, "beat": 1.5, "miss": -1.5,
    "outperform": 1.5, "underperform": -1.5, "recession": -2.0,
    "inflation": -1.0, "deflation": -0.5, "hawkish": -0.5,
    "dovish": 0.5, "stimulus": 1.0, "tightening": -1.0,
    "default": -2.5, "bankruptcy": -3.0, "profit": 1.5,
    "loss": -1.5, "growth": 1.5, "decline": -1.5,
    "accumulate": 1.0, "distribute": -0.5, "squeeze": 1.5,
    "capitulation": -2.0, "euphoria": 1.5, "panic": -2.0,
    "oversold": 1.0, "overbought": -0.5, "buy": 1.0, "sell": -1.0,
    "long": 0.5, "short": -0.5, "hodl": 1.0, "fud": -1.5,
    "ath": 1.5, "dip": -0.5, "correction": -1.0,
    "halving": 1.5, "whale": 0.5, "rug": -3.0, "scam": -3.0,
}


def _get_vader():
    """Lazy-load VADER with finance lexicon extensions."""
    global _vader
    if _vader is None:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            _vader = SentimentIntensityAnalyzer()
            _vader.lexicon.update(FINANCE_LEXICON)
            logger.debug("vader_loaded_with_finance_lexicon")
        except ImportError:
            logger.warning("vader_not_installed hint='pip install vaderSentiment'")
            return None
    return _vader


def score_vader(text: str) -> SentimentScore | None:
    """Fast VADER scoring with finance lexicon. Returns None if vaderSentiment is missing."""
    vader = _get_vader()
    if vader is None:
        return None

    start = time.monotonic()
    scores = vader.polarity_scores(text)
    elapsed = (time.monotonic() - start) * 1000

    compound = scores["compound"]
    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"

    confidence = min(abs(compound), 1.0)

    return SentimentScore(
        score=compound,
        confidence=confidence,
        model="vader_finance",
        label=label,
        elapsed_ms=round(elapsed, 1),
    )


def score_vader_compound(text: str) -> float:
    """Return only VADER's compound score (convenience for callers that don't need the full record)."""
    vader = _get_vader()
    if vader is None:
        return 0.0
    return float(vader.polarity_scores(text)["compound"])
