"""InferenceClient — HTTP client to the DGX inference service.

Routes FinBERT + LLM + embed + NER + translate + classify to
`NEWS_PIPELINE_INFERENCE_URL` (Tailscale-reachable DGX host). Provides:
  - batched score_finbert (primary cost-saver vs per-article calls)
  - retry with exponential backoff
  - degraded fallbacks (VADER for FinBERT, None/empty for NER/embed/translate)

Cloud code calls `get_client()` and uses its methods. If the URL env var is unset,
the client defaults to direct local calls where possible (keeps dev loop simple).
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import httpx


logger = logging.getLogger(__name__)


def _env_url() -> str:
    return os.getenv("NEWS_PIPELINE_INFERENCE_URL", "").rstrip("/")


def _env_token() -> str:
    return os.getenv("NEWS_PIPELINE_INFERENCE_TOKEN", "")


@dataclass
class InferenceClient:
    base_url: str = ""
    bearer_token: str = ""
    timeout: float = 30.0
    max_retries: int = 2
    batch_size: int = 64

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.bearer_token:
            h["Authorization"] = f"Bearer {self.bearer_token}"
        return h

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def _post(self, path: str, payload: dict) -> dict | list | None:
        """POST with retry. Returns parsed JSON or None on failure."""
        if not self.enabled:
            return None

        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as c:
                    resp = c.post(url, json=payload, headers=self._headers())
                    resp.raise_for_status()
                    return resp.json()
            except Exception as e:
                last_exc = e
                if attempt < self.max_retries:
                    backoff = 0.5 * (2 ** attempt)
                    logger.warning("inference_retry path=%s attempt=%d backoff=%.1fs err=%s",
                                   path, attempt + 1, backoff, e)
                    time.sleep(backoff)

        logger.error("inference_failed path=%s err=%s", path, last_exc)
        return None

    # ── FinBERT ──────────────────────────────────────────────────
    def score_finbert_batch(self, texts: list[str]) -> list[dict] | None:
        """Score a batch of texts. Returns list of {score, confidence, label, probs, elapsed_ms}.

        Automatically chunks into self.batch_size slices. Returns None on total failure
        so callers can fall back to VADER.
        """
        if not texts:
            return []
        if not self.enabled:
            return None

        out: list[dict] = []
        for i in range(0, len(texts), self.batch_size):
            chunk = texts[i : i + self.batch_size]
            resp = self._post("/v1/score/finbert", {"texts": chunk})
            if resp is None:
                return None
            out.extend(resp)
        return out

    def score_finbert_one(self, text: str) -> dict | None:
        """Score a single text, returning None on failure."""
        result = self.score_finbert_batch([text])
        return result[0] if result else None

    # ── LLM ──────────────────────────────────────────────────────
    def score_llm(self, text: str, *, context: str = "") -> dict | None:
        return self._post("/v1/score/llm", {"text": text, "context": context})

    # ── Embeddings ───────────────────────────────────────────────
    def embed_batch(self, texts: list[str]) -> list[list[float]] | None:
        if not texts:
            return []
        if not self.enabled:
            return None

        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            chunk = texts[i : i + self.batch_size]
            resp = self._post("/v1/embed", {"texts": chunk})
            if resp is None:
                return None
            out.extend(resp.get("vectors", []))
        return out

    # ── NER ──────────────────────────────────────────────────────
    def ner_batch(self, texts: list[str], *, lang: str = "en") -> list[list[dict]] | None:
        if not texts:
            return []
        if not self.enabled:
            return None

        out: list[list[dict]] = []
        for i in range(0, len(texts), self.batch_size):
            chunk = texts[i : i + self.batch_size]
            resp = self._post("/v1/ner", {"texts": chunk, "lang": lang})
            if resp is None:
                return None
            out.extend(resp)
        return out

    # ── Event classification ─────────────────────────────────────
    def classify_event(self, text: str, *, candidate_types: list[str] | None = None) -> dict | None:
        payload = {"text": text}
        if candidate_types:
            payload["candidate_types"] = candidate_types
        return self._post("/v1/classify/event", payload)

    # ── Translation ──────────────────────────────────────────────
    def translate(self, text: str, *, target_lang: str = "en", source_lang: str = "auto") -> dict | None:
        return self._post(
            "/v1/translate",
            {"text": text, "target_lang": target_lang, "source_lang": source_lang},
        )


_client: InferenceClient | None = None


def get_client() -> InferenceClient:
    """Return the process-wide InferenceClient (reads env on first call)."""
    global _client
    if _client is None:
        _client = InferenceClient(
            base_url=_env_url(),
            bearer_token=_env_token(),
            timeout=float(os.getenv("NEWS_PIPELINE_INFERENCE_TIMEOUT", "30")),
            max_retries=int(os.getenv("NEWS_PIPELINE_INFERENCE_RETRIES", "2")),
            batch_size=int(os.getenv("NEWS_PIPELINE_INFERENCE_BATCH", "64")),
        )
    return _client


def reset_client() -> None:
    """For tests: force re-read of env on next get_client()."""
    global _client
    _client = None
