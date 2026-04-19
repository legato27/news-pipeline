"""FinBERT scorer.

Routing:
  - If NEWS_PIPELINE_INFERENCE_URL is set → call DGX inference service (batched).
  - Else → run a local transformers.pipeline (Phase 1 behavior).

Two return-shape variants (for back-compat with both apps):
  - score_finbert(text) → SentimentScore | None     (polymarket-style)
  - score_finbert_compound(text) → float            (StockPrediction-style; pos - neg)
  - score_finbert_batch_compound(texts) → list[float]  (batched, primary perf path)
"""
from __future__ import annotations

import logging
import time

from news_pipeline.schema import SentimentScore
from news_pipeline.scoring.client import get_client


logger = logging.getLogger(__name__)

FINBERT_MODEL = "ProsusAI/finbert"

_sentiment_pipeline = None
_classification_pipeline = None


def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def _get_local_sentiment_pipeline():
    global _sentiment_pipeline
    if _sentiment_pipeline is None:
        try:
            from transformers import pipeline
            _sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model=FINBERT_MODEL,
                truncation=True,
                max_length=512,
            )
            logger.info("finbert_local_sentiment_pipeline_loaded")
        except Exception as e:
            logger.warning("finbert_local_sentiment_load_error err=%s", e)
            return None
    return _sentiment_pipeline


def _get_local_classification_pipeline():
    global _classification_pipeline
    if _classification_pipeline is None:
        try:
            from transformers import pipeline
            _classification_pipeline = pipeline(
                "text-classification",
                model=FINBERT_MODEL,
                top_k=None,
                device=0 if _cuda_available() else -1,
            )
            logger.info("finbert_local_classification_pipeline_loaded")
        except Exception as e:
            logger.warning("finbert_local_classification_load_error err=%s", e)
            return None
    return _classification_pipeline


def score_finbert(text: str) -> SentimentScore | None:
    """Single-text FinBERT → SentimentScore (polymarket-style).

    Tries DGX first; falls back to local pipeline if DGX is down or unset.
    Returns None if no scorer is available (composite should then drop this model).
    """
    client = get_client()
    if client.enabled:
        resp = client.score_finbert_one(text)
        if resp:
            return SentimentScore(
                score=float(resp["score"]),
                confidence=float(resp["confidence"]),
                model="finbert_dgx",
                label=resp["label"],
                elapsed_ms=float(resp.get("elapsed_ms", 0.0)),
            )
        # DGX failed — fall through to local

    pipe = _get_local_sentiment_pipeline()
    if pipe is None:
        return None

    start = time.monotonic()
    try:
        result = pipe(text[:512])[0]
        elapsed = (time.monotonic() - start) * 1000

        label = result["label"]
        confidence = result["score"]

        if label == "positive":
            score = confidence
        elif label == "negative":
            score = -confidence
        else:
            score = 0.0

        return SentimentScore(
            score=score,
            confidence=confidence,
            model="finbert",
            label=label,
            elapsed_ms=round(elapsed, 1),
        )
    except Exception as e:
        logger.warning("finbert_local_score_error err=%s", e)
        return None


def score_finbert_compound(text: str) -> float:
    """Single-text FinBERT → float in [-1, 1] (StockPrediction-style).

    Tries DGX, then local, then VADER as final fallback.
    """
    client = get_client()
    if client.enabled:
        resp = client.score_finbert_one(text)
        if resp is not None:
            return float(resp["score"])

    pipe = _get_local_classification_pipeline()
    if pipe is not None:
        try:
            results = pipe(text[:512])[0]
            label_scores = {r["label"]: r["score"] for r in results}
            return float(label_scores.get("positive", 0) - label_scores.get("negative", 0))
        except Exception:
            pass

    from news_pipeline.scoring.vader import score_vader_compound
    return score_vader_compound(text)


def score_finbert_batch_compound(texts: list[str]) -> list[float]:
    """Batched FinBERT → list of floats in [-1, 1].

    Primary performance path for Celery's per-cycle scoring. Falls back to VADER
    (per-text) if DGX and local FinBERT are both unavailable.
    """
    if not texts:
        return []

    client = get_client()
    if client.enabled:
        resp = client.score_finbert_batch(texts)
        if resp is not None:
            return [float(r["score"]) for r in resp]

    pipe = _get_local_classification_pipeline()
    if pipe is not None:
        try:
            results = pipe([t[:512] for t in texts])
            out: list[float] = []
            for r in results:
                label_scores = {row["label"]: row["score"] for row in r}
                out.append(float(label_scores.get("positive", 0) - label_scores.get("negative", 0)))
            return out
        except Exception as e:
            logger.warning("finbert_local_batch_error err=%s", e)

    from news_pipeline.scoring.vader import score_vader_compound
    return [score_vader_compound(t) for t in texts]
