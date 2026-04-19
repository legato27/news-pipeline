"""Composite scorer — confidence-weighted blend of VADER + FinBERT + optional LLM.

Extracted from polymarket-agent/sentiment/nlp_pipeline.score_text. Return shape
preserved for back-compat with aggregator and any downstream dict consumers.
"""
from __future__ import annotations

import logging

from news_pipeline.scoring.finbert import score_finbert
from news_pipeline.scoring.llm import score_llm
from news_pipeline.scoring.vader import score_vader


logger = logging.getLogger(__name__)


def score_text(
    text: str,
    use_finbert: bool = True,
    use_llm: bool = False,
    context: str = "",
) -> dict:
    """Run multi-model sentiment scoring pipeline.

    Pipeline:
      1. VADER (always — fast screen, <100 ms)
      2. FinBERT (if enabled — ~3 s on CPU)
      3. LLM (if enabled — ~5 s, complex/geopolitical)
      4. Blend: confidence-weighted average with fixed model weights
         (VADER 0.3, FinBERT 0.5, LLM 0.4).

    Returns dict with keys:
      composite_score, composite_label, composite_confidence, models, n_models
    """
    results: dict[str, dict] = {}
    scores: list[tuple[float, float, float]] = []  # (score, confidence, model_weight)

    vader_result = score_vader(text)
    if vader_result:
        results["vader"] = {
            "score": vader_result.score,
            "confidence": vader_result.confidence,
            "label": vader_result.label,
            "ms": vader_result.elapsed_ms,
        }
        scores.append((vader_result.score, vader_result.confidence, 0.3))

    if use_finbert:
        finbert_result = score_finbert(text)
        if finbert_result:
            results["finbert"] = {
                "score": finbert_result.score,
                "confidence": finbert_result.confidence,
                "label": finbert_result.label,
                "ms": finbert_result.elapsed_ms,
            }
            scores.append((finbert_result.score, finbert_result.confidence, 0.5))

    if use_llm:
        llm_result = score_llm(text, context=context)
        if llm_result:
            results["llm"] = {
                "score": llm_result.score,
                "confidence": llm_result.confidence,
                "label": llm_result.label,
                "ms": llm_result.elapsed_ms,
            }
            scores.append((llm_result.score, llm_result.confidence, 0.4))

    if scores:
        total_weight = sum(conf * weight for _, conf, weight in scores)
        if total_weight > 0:
            composite_score = sum(s * c * w for s, c, w in scores) / total_weight
        else:
            composite_score = 0.0

        avg_confidence = sum(c for _, c, _ in scores) / len(scores)

        if composite_score > 0.1:
            composite_label = "positive"
        elif composite_score < -0.1:
            composite_label = "negative"
        else:
            composite_label = "neutral"
    else:
        composite_score = 0.0
        avg_confidence = 0.0
        composite_label = "neutral"

    return {
        "composite_score": round(float(composite_score), 4),
        "composite_label": composite_label,
        "composite_confidence": round(float(avg_confidence), 4),
        "models": results,
        "n_models": len(results),
    }
