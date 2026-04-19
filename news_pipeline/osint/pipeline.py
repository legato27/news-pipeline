"""OSINT processing pipeline (Option A: vLLM + Qdrant + local spaCy).

Per unprocessed article:
  1. Translate non-English body to English via vLLM chat completion.
  2. NER on (title + translated body) via local spaCy.
  3. Resolve actors → osint_actors (upsert).
  4. Geolocate from source-native fields (GDELT/ACLED lat/lon) or
     matching/geo.py country centroid.
  5. Embed via vLLM embeddings.
  6. Search Qdrant for nearest article in last 72h; if cosine >= 0.88,
     attach to that event. Else create a new event.
  7. Upsert embedding into Qdrant with the final event_id + payload.
  8. Classify event_type from source-native codes (CAMEO/CVE/sanctions/
     reliefweb), else zero-shot via vLLM chat.
  9. Persist osint_events + osint_actor_events + osint_event_articles.

Graceful degradation: if vLLM, Qdrant, or spaCy is unavailable, articles still
land with event_id set but no embedding/actors. They can be reprocessed later
by re-running the task after re-enabling these modules (event_id rollback: set
back to NULL in SQL).
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from news_pipeline.clients import qdrant as qclient
from news_pipeline.clients.vllm import chat, chat_json, embed
from news_pipeline.matching.actors import resolve as resolve_actor
from news_pipeline.matching.geo import build_geojson_point, centroid_for_country
from news_pipeline.matching.lang import is_english
from news_pipeline.nlp.ner import ner_batch


logger = logging.getLogger(__name__)

EVENT_DEDUP_THRESHOLD = 0.88
EVENT_LOOKBACK_HOURS = 72

CAMEO_TO_EVENT_TYPE: dict[str, str] = {
    "01": "diplomatic", "02": "diplomatic", "03": "diplomatic", "04": "diplomatic",
    "05": "diplomatic", "06": "economic", "07": "humanitarian", "08": "diplomatic",
    "09": "diplomatic", "10": "diplomatic", "11": "diplomatic", "12": "diplomatic",
    "13": "diplomatic", "14": "protest", "15": "armed_conflict",
    "16": "sanctions_change", "17": "armed_conflict", "18": "armed_conflict",
    "19": "armed_conflict", "20": "armed_conflict",
}

CANDIDATE_EVENT_TYPES = [
    "armed_conflict", "protest", "cyber_advisory", "cyber_incident",
    "sanctions_change", "regulatory_action", "humanitarian",
    "diplomatic", "economic", "other",
]


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


def _point_id_for(content_hash: str) -> int:
    """Qdrant requires int or UUID ids. Use a stable 63-bit hash of content_hash."""
    return int(hashlib.md5(content_hash.encode()).hexdigest()[:15], 16)


def _translate(text: str, *, src_lang: str | None) -> str | None:
    """Translate text to English via vLLM chat. Returns None on failure."""
    prompt = (
        f"Translate the following text to English. Reply with ONLY the translation, "
        f"no preamble or explanation.\n\nText: {text[:2000]}"
    )
    return chat(prompt, temperature=0.0, max_tokens=800)


def _classify_event_llm(text: str) -> str:
    """Zero-shot event-type classification via vLLM chat."""
    types_list = ", ".join(CANDIDATE_EVENT_TYPES)
    prompt = (
        f"Classify the following text into ONE of these event types: {types_list}.\n"
        'Respond with ONLY: {"event_type": "<one of the types>", "confidence": <0-1>}\n\n'
        f"Text: {text[:1000]}"
    )
    data = chat_json(prompt, max_tokens=60)
    if not data:
        return "other"
    et = data.get("event_type", "other")
    return et if et in CANDIDATE_EVENT_TYPES else "other"


def _derive_event_type(article) -> tuple[str | None, str | None]:
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
        return "cyber_advisory", raw.get("cve_id")
    if src == "sanctions":
        return "sanctions_change", raw.get("programme") or raw.get("regime")
    if src == "reliefweb":
        return "humanitarian", None
    return None, None


def _derive_location(article) -> dict:
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
    if src == "gdelt" and str(raw.get("EventRootCode", ""))[:2] in ("18", "19", "20"):
        return "high"
    return "low"


def _verification_from_source(source_kind: str) -> str:
    return {
        "gdelt": "single_source", "reliefweb": "official", "cisa": "official",
        "sanctions": "official", "acled": "corroborated", "osint_rss": "single_source",
    }.get(source_kind, "unverified")


def process_batch(limit: int = 200) -> dict:
    """Process OsintArticle rows where event_id IS NULL. Returns stats dict."""
    from app.models.osint import (
        OsintArticle,
        OsintEvent,
        osint_actor_events,
        osint_event_articles,
    )

    session, engine = _sync_session()
    stats = {"selected": 0, "translated": 0, "nered": 0, "embedded": 0,
             "new_events": 0, "clustered": 0, "failed": 0}

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

        # --- 1. Translate non-English bodies via vLLM chat ------------------
        texts: list[str] = []
        for art in rows:
            body = f"{art.title or ''}. {art.summary or ''}".strip()
            needs_translation = (
                (art.language and art.language not in ("en", "auto"))
                or not is_english(body)
            )
            if needs_translation:
                translated = _translate(body, src_lang=art.language)
                if translated:
                    art.original_language = art.language or "auto"
                    art.translated_text = translated
                    art.language = "en"
                    body = translated
                    stats["translated"] += 1
            texts.append(body[:2000])

        # --- 2. NER (local spaCy) -------------------------------------------
        ner_results = ner_batch(texts)
        stats["nered"] = sum(1 for r in ner_results if r)

        # --- 3. Embeddings (vLLM) -------------------------------------------
        embeddings = embed(texts) or [None] * len(rows)
        stats["embedded"] = sum(1 for e in embeddings if e is not None)

        # --- 4. Per-article: cluster → event → persist ----------------------
        cutoff = datetime.now(timezone.utc) - timedelta(hours=EVENT_LOOKBACK_HOURS)

        for art, ents, emb in zip(rows, ner_results, embeddings):
            try:
                # Actor resolution
                actor_resolutions: list[tuple[str, str, str, str]] = []
                for ent in (ents or [])[:30]:
                    if ent["label"] not in ("PERSON", "ORG", "GPE", "LOC", "NORP"):
                        continue
                    actor_id, kind, name = resolve_actor(ent["text"], ent["label"])
                    _upsert_actor(session, actor_id, kind, name)
                    role = "location" if ent["label"] in ("GPE", "LOC") else "mentioned"
                    actor_resolutions.append((actor_id, kind, name, role))

                # Event clustering via Qdrant
                existing_event_id: str | None = None
                if emb is not None:
                    hits = qclient.search_similar(
                        emb,
                        limit=1,
                        score_threshold=EVENT_DEDUP_THRESHOLD,
                        fetched_after=cutoff,
                        require_event_id=True,
                    )
                    if hits:
                        existing_event_id = hits[0].get("event_id")

                if existing_event_id:
                    art.event_id = existing_event_id
                    stats["clustered"] += 1
                else:
                    # Derive event_type: source-native first, LLM zero-shot as fallback
                    event_type, event_code = _derive_event_type(art)
                    if not event_type:
                        event_type = _classify_event_llm(texts[rows.index(art)])

                    loc = _derive_location(art)
                    if loc["lat"] is None and loc["country_code"]:
                        centroid = centroid_for_country(loc["country_code"])
                        if centroid:
                            loc["lat"], loc["lon"] = centroid

                    event_id = str(uuid.uuid4())
                    event_hash = hashlib.md5(
                        (art.content_hash + (event_code or "")).encode()
                    ).hexdigest()
                    summary_text = (art.translated_text or art.title or "")[:500]

                    session.add(OsintEvent(
                        id=event_id,
                        event_hash=event_hash,
                        event_type=event_type,
                        event_code=str(event_code) if event_code else None,
                        urgency=_urgency_from_source(art),
                        verification_level=_verification_from_source(art.source_kind),
                        country_code=loc["country_code"] or None,
                        admin1=loc.get("admin1"),
                        location_name=loc.get("name"),
                        location_geojson=build_geojson_point(loc["lat"], loc["lon"]),
                        occurred_at=art.published_at,
                        summary=summary_text,
                        primary_article_url=art.url,
                    ))
                    art.event_id = event_id
                    stats["new_events"] += 1

                # FLUSH so the OsintEvent (and any new OsintActor adds) are visible
                # before we execute the m2m inserts whose FKs reference them.
                session.flush()

                # Now FK-safe: link article ↔ event
                session.execute(
                    osint_event_articles.insert().values(
                        event_id=art.event_id, content_hash=art.content_hash
                    ).prefix_with("ON CONFLICT DO NOTHING", dialect="postgresql")
                )

                # Qdrant upsert (only after event_id is known)
                if emb is not None:
                    qclient.upsert_article(
                        _point_id_for(art.content_hash),
                        emb,
                        content_hash=art.content_hash,
                        event_id=art.event_id,
                        fetched_at=art.fetched_at,
                        source_kind=art.source_kind,
                        title=art.title,
                    )

                # Link actors to the event (actors were added earlier in this
                # iteration and are already flushed by the flush above).
                for actor_id, _kind, _name, role in actor_resolutions:
                    session.execute(
                        osint_actor_events.insert().values(
                            actor_id=actor_id, event_id=art.event_id, role=role
                        ).prefix_with("ON CONFLICT DO NOTHING", dialect="postgresql")
                    )
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
