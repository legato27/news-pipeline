"""Qdrant client for OSINT article embeddings.

Existing Qdrant instance at :6333 is shared across KG + knowledge collections.
We add `osint_articles` for OSINT event-dedup clustering.

Env:
  QDRANT_URL                  default http://host.docker.internal:6333
  QDRANT_OSINT_COLLECTION     default osint_articles
  QDRANT_OSINT_VECTOR_SIZE    default 768 (nomic-embed-text)

A single lazy singleton QdrantClient is shared per process to avoid connection
churn. ensure_collection() is idempotent.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_client = None


def _url() -> str:
    return os.getenv("QDRANT_URL", "http://host.docker.internal:6333")


def _collection() -> str:
    return os.getenv("QDRANT_OSINT_COLLECTION", "osint_articles")


def _vector_size() -> int:
    return int(os.getenv("QDRANT_OSINT_VECTOR_SIZE", "768"))


def get_client():
    """Return the shared QdrantClient. Import is lazy so the module works even
    if qdrant-client isn't installed (degraded mode)."""
    global _client
    if _client is None:
        try:
            from qdrant_client import QdrantClient
            _client = QdrantClient(url=_url())
        except ImportError:
            logger.warning("qdrant_client_not_installed hint='pip install qdrant-client'")
            return None
    return _client


def ensure_collection() -> bool:
    """Create the OSINT collection if missing. Returns True if ready, False on error."""
    client = get_client()
    if client is None:
        return False

    try:
        from qdrant_client.http.models import Distance, VectorParams

        existing = {c.name for c in client.get_collections().collections}
        if _collection() not in existing:
            client.create_collection(
                collection_name=_collection(),
                vectors_config=VectorParams(size=_vector_size(), distance=Distance.COSINE),
            )
            logger.info("qdrant_collection_created name=%s dim=%d", _collection(), _vector_size())
        return True
    except Exception as e:
        logger.warning("qdrant_ensure_collection_failed err=%s", e)
        return False


def upsert_article(
    point_id: str | int,
    vector: list[float],
    *,
    content_hash: str,
    event_id: str | None = None,
    fetched_at: datetime | None = None,
    source_kind: str | None = None,
    title: str | None = None,
) -> bool:
    """Upsert a single article embedding."""
    client = get_client()
    if client is None:
        return False
    if not ensure_collection():
        return False

    try:
        from qdrant_client.http.models import PointStruct

        payload: dict[str, Any] = {"content_hash": content_hash}
        if event_id:
            payload["event_id"] = event_id
        if fetched_at:
            payload["fetched_at_epoch"] = int(fetched_at.timestamp())
        if source_kind:
            payload["source_kind"] = source_kind
        if title:
            payload["title"] = title[:300]

        client.upsert(
            collection_name=_collection(),
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )
        return True
    except Exception as e:
        logger.warning("qdrant_upsert_failed id=%s err=%s", point_id, e)
        return False


def search_similar(
    vector: list[float],
    *,
    limit: int = 5,
    score_threshold: float = 0.88,
    fetched_after: datetime | None = None,
    require_event_id: bool = True,
) -> list[dict]:
    """Return points with cosine score >= threshold, optionally filtered by freshness
    and by having an attached event_id.

    Returns list of {id, score, content_hash, event_id, fetched_at_epoch, ...}.
    """
    client = get_client()
    if client is None:
        return []
    if not ensure_collection():
        return []

    try:
        from qdrant_client.http.models import (
            FieldCondition,
            Filter,
            IsNullCondition,
            PayloadField,
            Range,
        )

        must: list = []
        must_not: list = []

        if require_event_id:
            # event_id field must be present AND not null
            must_not.append(IsNullCondition(is_null=PayloadField(key="event_id")))

        if fetched_after is not None:
            must.append(
                FieldCondition(
                    key="fetched_at_epoch",
                    range=Range(gte=int(fetched_after.timestamp())),
                )
            )

        qfilter = Filter(must=must or None, must_not=must_not or None) if (must or must_not) else None

        results = client.query_points(
            collection_name=_collection(),
            query=vector,
            limit=limit,
            score_threshold=score_threshold,
            query_filter=qfilter,
            with_payload=True,
        )
        # qdrant-client 1.x returns QueryResponse with .points
        points = getattr(results, "points", results)
        return [
            {"id": p.id, "score": p.score, **(p.payload or {})}
            for p in points
        ]
    except Exception as e:
        logger.warning("qdrant_search_failed err=%s", e)
        return []
