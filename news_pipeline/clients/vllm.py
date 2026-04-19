"""vLLM client — OpenAI-compatible chat + embeddings.

The cluster runs two vLLM servers on this DGX box:
  - vllm-inference  (:30100) — chat/completions, default model google/gemma-4-26B-A4B-it
  - vllm-embeddings (:30200) — embeddings, default model /models/nomic-embed-text

Both speak OpenAI /v1/* protocol, so we reuse a single thin httpx client.
Env overrides:
  NEWS_PIPELINE_LLM_URL       chat completions endpoint (default host.docker.internal:30100)
  NEWS_PIPELINE_LLM_MODEL     chat model name
  NEWS_PIPELINE_EMBED_URL     embeddings endpoint (default host.docker.internal:30200)
  NEWS_PIPELINE_EMBED_MODEL   embedding model name
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

import httpx


logger = logging.getLogger(__name__)


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _chat_url() -> str:
    return _env(
        "NEWS_PIPELINE_LLM_URL",
        "http://host.docker.internal:30100/v1/chat/completions",
    )


def _chat_model() -> str:
    return _env("NEWS_PIPELINE_LLM_MODEL", "google/gemma-4-26B-A4B-it")


def _embed_url() -> str:
    return _env(
        "NEWS_PIPELINE_EMBED_URL",
        "http://host.docker.internal:30200/v1/embeddings",
    )


def _embed_model() -> str:
    return _env("NEWS_PIPELINE_EMBED_MODEL", "/models/nomic-embed-text")


def chat(
    prompt: str,
    *,
    system: str = "",
    temperature: float = 0.1,
    max_tokens: int = 200,
    timeout: float = 30.0,
) -> str | None:
    """Send a single-turn prompt, return assistant message content. None on failure."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        with httpx.Client(timeout=timeout) as c:
            resp = c.post(
                _chat_url(),
                json={
                    "model": _chat_model(),
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("vllm_chat_failed err=%s", e)
        return None


def chat_json(
    prompt: str,
    *,
    system: str = "You respond with ONLY valid JSON, no prose.",
    **kwargs,
) -> dict | None:
    """Convenience: chat + extract first JSON object from the response."""
    content = chat(prompt, system=system, **kwargs)
    if not content:
        return None
    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except Exception:
        logger.warning("vllm_chat_json_parse_failed content=%s", content[:200])
        return None


def embed(texts: list[str], *, timeout: float = 30.0, batch_size: int = 64) -> list[list[float]] | None:
    """Batched embeddings via vLLM /v1/embeddings. Returns None on total failure."""
    if not texts:
        return []

    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        chunk = [t[:2000] for t in texts[i : i + batch_size]]
        try:
            with httpx.Client(timeout=timeout) as c:
                resp = c.post(
                    _embed_url(),
                    json={"model": _embed_model(), "input": chunk},
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
        except Exception as e:
            logger.warning("vllm_embed_failed err=%s", e)
            return None

        for item in data:
            emb = item.get("embedding")
            if emb:
                out.append(emb)

    return out
