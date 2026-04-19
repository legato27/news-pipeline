"""Language detection — lightweight heuristic.

Extracted from Project-StockPrediction/.../services/sentiment/rss_crawler.is_english.
"""
from __future__ import annotations


def is_english(text: str) -> bool:
    """Fast heuristic to detect if text is English.

    Checks ASCII ratio + presence of common English markers.
    """
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    ratio = ascii_count / len(text) if text else 0
    if ratio < 0.85:
        return False
    lower = text.lower()
    en_markers = ["the ", " is ", " are ", " was ", " has ", " for ", " and ", " that ", " with "]
    hits = sum(1 for m in en_markers if m in lower)
    return hits >= 2 or (ratio > 0.95 and len(text) > 20)
