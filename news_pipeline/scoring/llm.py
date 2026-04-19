"""LLM scorer via Ollama (qwen3.5 by default).

Routing:
  - If NEWS_PIPELINE_INFERENCE_URL set → call DGX /v1/score/llm.
  - Else → call Ollama directly (polymarket legacy behavior).
"""
from __future__ import annotations

import json
import logging
import re
import time

import httpx

from news_pipeline.schema import SentimentScore
from news_pipeline.scoring.client import get_client


logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:30100/v1/chat/completions"
DEFAULT_MODEL = "qwen3.5"


def score_llm(
    text: str,
    *,
    context: str = "",
    ollama_url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_MODEL,
    timeout: float = 30.0,
) -> SentimentScore | None:
    """LLM-based sentiment. Tries DGX first (if configured), then local Ollama."""
    client = get_client()
    if client.enabled:
        resp = client.score_llm(text, context=context)
        if resp:
            return SentimentScore(
                score=float(resp["score"]),
                confidence=float(resp["confidence"]),
                model="llm_dgx",
                label=resp.get("label", "neutral"),
                elapsed_ms=float(resp.get("elapsed_ms", 0.0)),
            )

    # Direct Ollama call (legacy path)
    try:
        prompt = (
            "Analyze the financial sentiment of this text.\n"
            "Respond with ONLY a JSON object: "
            '{"score": <float -1.0 to 1.0>, "label": "<positive|negative|neutral>", '
            '"confidence": <float 0.0 to 1.0>}\n\n'
            f"Text: {text[:500]}\n"
            f"{f'Context: {context[:200]}' if context else ''}"
        )

        start = time.monotonic()
        with httpx.Client(timeout=timeout) as c:
            resp = c.post(
                ollama_url,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 100,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        elapsed = (time.monotonic() - start) * 1000

        json_match = re.search(r"\{[^}]+\}", content)
        if json_match:
            data = json.loads(json_match.group())
            return SentimentScore(
                score=float(data.get("score", 0)),
                confidence=float(data.get("confidence", 0.5)),
                model=f"llm_{model}",
                label=data.get("label", "neutral"),
                elapsed_ms=round(elapsed, 1),
            )
    except Exception as e:
        logger.warning("llm_sentiment_error err=%s", e)

    return None
