"""EU consolidated sanctions list ingest.

Public XML feed at https://webgate.ec.europa.eu/fsd/fsf (requires registration
for direct download URL). The consolidated list is also mirrored at:
  https://data.europa.eu/api/hub/store/data/consolidated-list-of-sanctions-measures

Set EU_SANCTIONS_URL env var to the concrete download URL your tenant uses.
"""
from __future__ import annotations

import hashlib
import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx


logger = logging.getLogger(__name__)


def fetch_recent(*, prior_ids: set[str] | None = None, timeout: float = 30.0) -> list[dict]:
    url = os.getenv("EU_SANCTIONS_URL", "")
    if not url:
        logger.debug("eu_sanctions_url_missing")
        return []

    try:
        with httpx.Client(timeout=timeout) as c:
            resp = c.get(url)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
    except Exception as e:
        logger.warning("eu_sanctions_fetch_failed err=%s", e)
        return []

    # Structure varies; we try the documented `sanctionEntity` element.
    articles: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for ent in root.iter():
        tag = ent.tag.split("}")[-1]
        if tag != "sanctionEntity":
            continue

        logical_id = ent.attrib.get("logicalId") or ent.attrib.get("id") or ""
        if prior_ids is not None and logical_id in prior_ids:
            continue

        name_el = ent.find(".//{*}nameAlias")
        name = name_el.attrib.get("wholeName", "").strip() if name_el is not None else ""
        if not name:
            continue

        programme = ""
        for reg in ent.iter():
            if reg.tag.split("}")[-1] == "regulation":
                programme = reg.attrib.get("programme", "")
                break

        title = f"[EU sanctions added] {name} — {programme}".strip(" —")
        url_detail = f"https://webgate.ec.europa.eu/fsd/fsf#!/entity/{logical_id}"
        content_hash = hashlib.md5(f"eu_sanctions_{logical_id}".encode()).hexdigest()

        articles.append({
            "content_hash": content_hash,
            "title": title[:500],
            "summary": title,
            "text": title,
            "url": url_detail,
            "source": "eu_sanctions",
            "source_kind": "sanctions",
            "published_at": now,
            "language": "en",
            "raw": {"logical_id": logical_id, "programme": programme},
        })

    logger.info("eu_sanctions_delta articles=%d", len(articles))
    return articles
