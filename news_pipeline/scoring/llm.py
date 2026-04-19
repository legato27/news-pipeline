"""LLM sentiment scorer via vLLM (OpenAI-compatible).

Uses `news_pipeline.clients.vllm.chat_json` by default (pointing at vllm-inference
on :30100). Env vars control the endpoint + model. Returns a SentimentScore
with `model = "llm_<model_id>"`.
"""
from __future__ import annotations

import logging
import time

from news_pipeline.clients.vllm import chat_json, _chat_model
from news_pipeline.schema import SentimentScore


logger = logging.getLogger(__name__)


_PROMPT = (
    "Analyze the financial sentiment of this text. "
    'Respond with ONLY a JSON object: '
    '{"score": <float -1.0 to 1.0>, "label": "<positive|negative|neutral>", '
    '"confidence": <float 0.0 to 1.0>}\n\n'
    "Text: {text}\n"
    "{ctx}"
)


def score_llm(text: str, *, context: str = "", **_legacy_kwargs) -> SentimentScore | None:
    """LLM-based sentiment. Returns None on failure (composite scorer will drop it)."""
    prompt = _PROMPT.format(
        text=text[:500],
        ctx=(f"Context: {context[:200]}" if context else ""),
    )

    start = time.monotonic()
    data = chat_json(prompt, max_tokens=100)
    elapsed = (time.monotonic() - start) * 1000

    if not data:
        return None

    try:
        return SentimentScore(
            score=float(data.get("score", 0)),
            confidence=float(data.get("confidence", 0.5)),
            model=f"llm_{_chat_model()}",
            label=data.get("label", "neutral"),
            elapsed_ms=round(elapsed, 1),
        )
    except Exception as e:
        logger.warning("score_llm_parse_error data=%s err=%s", data, e)
        return None
