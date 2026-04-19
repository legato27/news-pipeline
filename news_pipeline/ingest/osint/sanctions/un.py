"""UN Security Council consolidated sanctions list.

Public XML feed at https://scsanctions.un.org/resources/xml/en/consolidated.xml
"""
from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx


logger = logging.getLogger(__name__)

UN_CONSOLIDATED_XML = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"


def fetch_recent(*, prior_ids: set[str] | None = None, timeout: float = 30.0) -> list[dict]:
    try:
        with httpx.Client(timeout=timeout) as c:
            resp = c.get(UN_CONSOLIDATED_XML)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
    except Exception as e:
        logger.warning("un_sanctions_fetch_failed err=%s", e)
        return []

    articles: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for ind in root.iter():
        tag = ind.tag.split("}")[-1]
        if tag not in ("INDIVIDUAL", "ENTITY"):
            continue

        ref = ind.findtext("REFERENCE_NUMBER") or ind.findtext("DATAID") or ""
        if not ref or (prior_ids is not None and ref in prior_ids):
            continue

        name_parts = [
            (ind.findtext(f) or "").strip()
            for f in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "NAME_ORIGINAL_SCRIPT", "FIRST_NAME")
        ]
        name = " ".join(p for p in name_parts if p).strip()
        committee = ind.findtext("UN_LIST_TYPE") or ""

        title = f"[UNSC sanctions added] {name} — {committee}".strip(" —")
        url_detail = f"https://www.un.org/securitycouncil/sanctions/information#{ref}"
        content_hash = hashlib.md5(f"un_sanctions_{ref}".encode()).hexdigest()

        articles.append({
            "content_hash": content_hash,
            "title": title[:500],
            "summary": title,
            "text": title,
            "url": url_detail,
            "source": "un_sanctions",
            "source_kind": "sanctions",
            "published_at": now,
            "language": "en",
            "raw": {"reference_number": ref, "entity_kind": tag, "committee": committee},
        })

    logger.info("un_sanctions_delta articles=%d", len(articles))
    return articles
