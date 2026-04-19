"""OSINT processing pipeline.

Per unprocessed article:
  1. Translate non-English body to English via DGX /v1/translate.
  2. NER on (title + translated summary) via DGX /v1/ner.
  3. Resolve actors with matching/actors.py; enrich/upsert osint_actors.
  4. Geolocate: prefer source-provided lat/lon (GDELT/ACLED), fall back to
     matching/geo.py centroid from NER country.
  5. Embed text via DGX /v1/embed; try to cluster into an existing event by
     cosine similarity ≥ EVENT_DEDUP_THRESHOLD within the last 72h.
  6. Classify event_type (zero-shot LLM via DGX /v1/classify/event); map from
     source-native codes when available (CAMEO, CVE prefix).
  7. Verification level from source + corroboration count.
  8. Persist OsintEvent (if new) + OsintActorEvent + OsintEventArticle; set
     OsintArticle.event_id so this article is not reprocessed.

Everything is graceful-degrading: if DGX is down the pipeline still lands
articles with empty actors/event, so future runs can re-enrich.

Compute lives on DGX via `news_pipeline.scoring.client.InferenceClient`.
Storage is cloud-side (Postgres w/ pgvector + PostGIS).
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable

from news_pipeline.matching.actors import resolve as resolve_actor
from news_pipeline.matching.geo import build_geojson_point, centroid_for_country
from news_pipeline.matching.lang import is_english
from news_pipeline.scoring.client import get_client


logger = logging.getLogger(__name__)

EVENT_DEDUP_THRESHOLD = 0.88   # cosine similarity above which we cluster into an existing event
EVENT_LOOKBACK_HOURS = 72

# CAMEO root-code → event_type (small mapping; extend as needed)
CAMEO_TO_EVENT_TYPE: dict[str, str] = {
    "01": "diplomatic",   # MAKE PUBLIC STATEMENT
    "02": "diplomatic",   # APPEAL
    "03": "diplomatic",   # EXPRESS INTENT TO COOPERATE
    "04": "diplomatic",   # CONSULT
    "05": "diplomatic",   # ENGAGE IN DIPLOMATIC COOPERATION
    "06": "economic",     # ENGAGE IN MATERIAL COOPERATION
    "07": "humanitarian", # PROVIDE AID
    "08": "diplomatic",   # YIELD
    "09": "diplomatic",   # INVESTIGATE
    "10": "diplomatic",   # DEMAND
    "11": "diplomatic",   # DISAPPROVE
    "12": "diplomatic",   # REJECT
    "13": "diplomatic",   # THREATEN
    "14": "protest",      # PROTEST
    "15": "armed_conflict", # EXHIBIT FORCE POSTURE
    "16": "sanctions_change", # REDUCE RELATIONS
    "17": "armed_conflict", # COERCE
    "18": "armed_conflict", # ASSAULT
    "19": "armed_conflict", # FIGHT
    "20": "armed_conflict", # USE UNCONVENTIONAL MASS VIOLENCE
}


def _sync_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings
    engine = create_engine(settings.database_url_sync)
    return sessionmaker(bind=engine)(), engine


def _upsert_actor(session, actor_id: str, kind: str, name: str) -> None:
    from app.models.osint import OsintActor

    existing = session.query(OsintActor).filter_by(id=actor_id).first()
    if existing:
        return
    session.add(OsintActor(id=actor_id, kind=kind, name=name[:500]))


def _find_similar_event(session, embedding: list[float]) -> str | None:
    """Query pgvector HNSW for nearest OsintEvent primary_article embedding.

    Uses the article's own embedding and returns the event_id of the nearest
    article within EVENT_LOOKBACK_HOURS and above EVENT_DEDUP_THRESHOLD.
    """
    from sqlalchemy import text

    cutoff = datetime.now(timezone.utc) - timedelta(hours=EVENT_LOOKBACK_HOURS)
    # <=> is pgvector's cosine distance operator; 1 - dist = similarity
    result = session.execute(
        text("""
            SELECT event_id, 1 - (embedding <=> (:emb)::vector) AS sim
            FROM osint_articles
            WHERE event_id IS NOT NULL
              AND embedding IS NOT NULL
              AND fetched_at >= :cutoff
            ORDER BY embedding <=> (:emb)::vector
            LIMIT 1
        """),
        {"emb": embedding, "cutoff": cutoff},
    ).first()
    if not result:
        return None
    event_id, sim = result
    return event_id if sim is not None and sim >= EVENT_DEDUP_THRESHOLD else None


def _derive_event_type(article) -> tuple[str | None, str | None]:
    """Return (event_type, event_code) from source-native fields when possible."""
    raw = article.raw or {}
    src = article.source_kind

    if src == "gdelt":
        root = raw.get("EventRootCode") or raw.get("EventBaseCode")
        if root:
            et = CAMEO_TO_EVENT_TYPE.get(str(root).zfill(2))
            return et, str(raw.get("EventCode", root))
    if src == "acled":
        return "armed_conflict", raw.get("event_type")
    if src == "cisa":
        cve = raw.get("cve_id")
        return "cyber_advisory", cve
    if src == "sanctions":
        return "sanctions_change", raw.get("programme") or raw.get("regime")
    if src == "reliefweb":
        return "humanitarian", None

    return None, None


def _derive_location(article) -> dict:
    """Return {lat, lon, country_code, admin1, name} best-effort."""
    raw = article.raw or {}
    src = article.source_kind

    if src == "gdelt":
        lat = raw.get("ActionGeo_Lat")
        lon = raw.get("ActionGeo_Long")
        return {
            "lat": float(lat) if lat else None,
            "lon": float(lon) if lon else None,
            "country_code": raw.get("ActionGeo_CountryCode"),
            "admin1": raw.get("ActionGeo_ADM1Code"),
            "name": raw.get("ActionGeo_FullName"),
        }
    if src == "acled":
        return {
            "lat": raw.get("lat"),
            "lon": raw.get("lon"),
            "country_code": _country_iso(raw.get("country")),
            "admin1": None,
            "name": raw.get("location"),
        }
    return {"lat": None, "lon": None, "country_code": None, "admin1": None, "name": None}


def _country_iso(name: str | None) -> str | None:
    if not name:
        return None
    from news_pipeline.matching.actors import COUNTRY_NAME_TO_CODE
    return COUNTRY_NAME_TO_CODE.get(name.lower())


def _urgency_from_source(article) -> str:
    src = article.source_kind
    raw = article.raw or {}
    if src == "acled" and int(raw.get("fatalities", 0) or 0) > 10:
        return "critical"
    if src == "cisa" and raw.get("known_ransomware") == "Known":
        return "high"
    if src == "sanctions":
        return "medium"
    if src in ("gdelt",) and raw.get("EventRootCode", "")[:2] in ("18", "19", "20"):
        return "high"
    return "low"


def _verification_from_source(source_kind: str) -> str:
    return {
        "gdelt": "single_source",
        "reliefweb": "official",
        "cisa": "official",
        "sanctions": "official",
        "acled": "corroborated",
        "osint_rss": "single_source",
    }.get(source_kind, "unverified")


def process_batch(limit: int = 200) -> dict:
    """Process OsintArticle rows where event_id IS NULL.

    Returns stats dict.
    """
    from app.models.osint import (
        OsintArticle,
        OsintEvent,
        osint_actor_events,
        osint_event_articles,
    )

    client = get_client()
    session, engine = _sync_session()
    stats = {"selected": 0, "translated": 0, "nered": 0, "new_events": 0, "clustered": 0, "failed": 0}

    try:
        rows = (
            session.query(OsintArticle)
            .filter(OsintArticle.event_id.is_(None))
            .order_by(OsintArticle.fetched_at.desc())
            .limit(limit)
            .all()
        )
        stats["selected"] = len(rows)
        if not rows:
            return stats

        # Prepare text for downstream calls; translate non-English if possible.
        texts_for_inference: list[str] = []
        for art in rows:
            body = f"{art.title or ''}. {art.summary or ''}".strip()
            if art.language and art.language not in ("en", "auto") and client.enabled:
                tr = client.translate(body, target_lang="en", source_lang=art.language)
                if tr and tr.get("text"):
                    art.original_language = art.language
                    art.translated_text = tr["text"]
                    art.language = "en"
                    body = tr["text"]
                    stats["translated"] += 1
            elif not is_english(body) and client.enabled:
                tr = client.translate(body, target_lang="en")
                if tr and tr.get("text"):
                    art.original_language = art.language or "auto"
                    art.translated_text = tr["text"]
                    art.language = "en"
                    body = tr["text"]
                    stats["translated"] += 1
            texts_for_inference.append(body[:2000])

        # NER in batch.
        ner_results = client.ner_batch(texts_for_inference) if client.enabled else [[] for _ in rows]
        ner_results = ner_results or [[] for _ in rows]
        stats["nered"] = sum(1 for r in ner_results if r)

        # Embeddings in batch.
        embeddings = client.embed_batch(texts_for_inference) if client.enabled else [None] * len(rows)
        embeddings = embeddings or [None] * len(rows)

        for art, ents, emb in zip(rows, ner_results, embeddings):
            try:
                # Save embedding
                if emb is not None:
                    session.execute(
                        __import__("sqlalchemy").text(
                            "UPDATE osint_articles SET embedding = (:emb)::vector WHERE content_hash = :ch"
                        ),
                        {"emb": emb, "ch": art.content_hash},
                    )

                # Actors from NER
                actor_resolutions: list[tuple[str, str, str, str]] = []  # (actor_id, kind, name, role)
                for ent in ents[:30]:
                    if ent["label"] not in ("PERSON", "ORG", "GPE", "LOC", "NORP"):
                        continue
                    actor_id, kind, name = resolve_actor(ent["text"], ent["label"])
                    _upsert_actor(session, actor_id, kind, name)
                    role = "location" if ent["label"] in ("GPE", "LOC") else "mentioned"
                    actor_resolutions.append((actor_id, kind, name, role))

                # Event clustering
                existing_event_id: str | None = None
                if emb is not None:
                    existing_event_id = _find_similar_event(session, emb)

                if existing_event_id:
                    art.event_id = existing_event_id
                    session.execute(
                        osint_event_articles.insert().values(
                            event_id=existing_event_id, content_hash=art.content_hash
                        ).prefix_with("ON CONFLICT DO NOTHING", dialect="postgresql")
                    )
                    stats["clustered"] += 1
                else:
                    # New event
                    event_type, event_code = _derive_event_type(art)
                    if not event_type and client.enabled:
                        resp = client.classify_event(texts_for_inference[rows.index(art)])
                        event_type = resp["event_type"] if resp else "other"
                    event_type = event_type or "other"

                    loc = _derive_location(art)
                    if not loc["lat"] and loc["country_code"]:
                        centroid = centroid_for_country(loc["country_code"])
                        if centroid:
                            loc["lat"], loc["lon"] = centroid

                    geojson = build_geojson_point(loc["lat"], loc["lon"])
                    event_id = str(uuid.uuid4())
                    event_hash = hashlib.md5((art.content_hash + (event_code or "")).encode()).hexdigest()

                    # Summary: first sentence of body (LLM synthesis is optional, deferred)
                    summary_text = (art.translated_text or art.title or "")[:500]

                    session.add(OsintEvent(
                        id=event_id,
                        event_hash=event_hash,
                        event_type=event_type,
                        event_code=str(event_code) if event_code else None,
                        urgency=_urgency_from_source(art),
                        verification_level=_verification_from_source(art.source_kind),
                        country_code=(loc["country_code"] or None) if loc["country_code"] else None,
                        admin1=loc.get("admin1"),
                        location_name=loc.get("name"),
                        location_geojson=geojson,
                        occurred_at=art.published_at,
                        summary=summary_text,
                        primary_article_url=art.url,
                    ))
                    if loc["lat"] is not None and loc["lon"] is not None:
                        session.execute(
                            __import__("sqlalchemy").text(
                                "UPDATE osint_events SET location = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography WHERE id = :id"
                            ),
                            {"lon": loc["lon"], "lat": loc["lat"], "id": event_id},
                        )
                    art.event_id = event_id
                    session.execute(
                        osint_event_articles.insert().values(
                            event_id=event_id, content_hash=art.content_hash
                        )
                    )
                    stats["new_events"] += 1

                # Link actors to the event
                for actor_id, _kind, _name, role in actor_resolutions:
                    session.execute(
                        osint_actor_events.insert().values(
                            actor_id=actor_id, event_id=art.event_id, role=role
                        ).prefix_with("ON CONFLICT DO NOTHING", dialect="postgresql")
                    )

                session.flush()
            except Exception as e:
                session.rollback()
                stats["failed"] += 1
                logger.exception("osint_process_article_failed hash=%s err=%s", art.content_hash, e)

        session.commit()
    finally:
        session.close()
        engine.dispose()

    logger.info("osint_process_batch stats=%s", stats)
    return stats
