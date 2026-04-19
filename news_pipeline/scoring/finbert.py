"""FinBERT scorer — runs in-process.

Two return-shape variants for back-compat with both consumer apps:
  - score_finbert(text)                -> SentimentScore | None     (polymarket)
  - score_finbert_compound(text)       -> float                     (StockPrediction)
  - score_finbert_batch_compound(txt)  -> list[float]               (batched perf path)

FinBERT runs locally via transformers.pipeline. If the model fails to load, the
compound variants fall back to VADER so the Celery task still completes.
"""
from __future__ import annotations

import logging
import time

from news_pipeline.schema import SentimentScore


logger = logging.getLogger(__name__)

FINBERT_MODEL = "ProsusAI/finbert"

_sentiment_pipeline = None       # top-1 label path (polymarket-style)
_classification_pipeline = None  # full label-scores path (StockPrediction-style)


def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def _get_sentiment_pipeline():
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
            logger.info("finbert_sentiment_pipeline_loaded")
        except Exception as e:
            logger.warning("finbert_sentiment_load_error err=%s", e)
            return None
    return _sentiment_pipeline


def _get_classification_pipeline():
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
            logger.info("finbert_classification_pipeline_loaded")
        except Exception as e:
            logger.warning("finbert_classification_load_error err=%s", e)
            return None
    return _classification_pipeline


def score_finbert(text: str) -> SentimentScore | None:
    pipe = _get_sentiment_pipeline()
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
        logger.warning("finbert_score_error err=%s", e)
        return None


def score_finbert_compound(text: str) -> float:
    """FinBERT positive-minus-negative. Falls back to VADER compound if pipeline fails."""
    pipe = _get_classification_pipeline()
    if pipe is None:
        from news_pipeline.scoring.vader import score_vader_compound
        return score_vader_compound(text)

    try:
        results = pipe(text[:512])[0]
        label_scores = {r["label"]: r["score"] for r in results}
        return float(label_scores.get("positive", 0) - label_scores.get("negative", 0))
    except Exception:
        from news_pipeline.scoring.vader import score_vader_compound
        return score_vader_compound(text)


def score_finbert_batch_compound(texts: list[str]) -> list[float]:
    """Primary perf path for Celery. Pipeline call is batched by transformers."""
    if not texts:
        return []

    pipe = _get_classification_pipeline()
    if pipe is None:
        from news_pipeline.scoring.vader import score_vader_compound
        return [score_vader_compound(t) for t in texts]

    try:
        results = pipe([t[:512] for t in texts])
        out: list[float] = []
        for r in results:
            label_scores = {row["label"]: row["score"] for row in r}
            out.append(float(label_scores.get("positive", 0) - label_scores.get("negative", 0)))
        return out
    except Exception as e:
        logger.warning("finbert_batch_error err=%s", e)
        from news_pipeline.scoring.vader import score_vader_compound
        return [score_vader_compound(t) for t in texts]
