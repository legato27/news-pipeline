"""Legacy InferenceClient shim.

Phase 2 shipped a DGX inference microservice on :30200 that this client was
meant to talk to. Phase 2a (Option A) retired that service in favor of the
existing vLLM + Qdrant infrastructure. Direct use of
`news_pipeline.clients.{vllm,qdrant}` and `news_pipeline.nlp.ner` is preferred.

This shim exists so any lingering `from news_pipeline.scoring.client import
get_client` imports continue to resolve. `.enabled` is False so no code paths
fall back to expecting a DGX service.
"""
from __future__ import annotations


class InferenceClient:
    enabled = False

    def score_finbert_batch(self, *_args, **_kwargs):
        return None

    def score_finbert_one(self, *_args, **_kwargs):
        return None

    def score_llm(self, *_args, **_kwargs):
        return None

    def embed_batch(self, *_args, **_kwargs):
        return None

    def ner_batch(self, *_args, **_kwargs):
        return None

    def classify_event(self, *_args, **_kwargs):
        return None

    def translate(self, *_args, **_kwargs):
        return None


_client = InferenceClient()


def get_client() -> InferenceClient:
    return _client


def reset_client() -> None:
    pass
