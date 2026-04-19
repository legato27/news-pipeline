"""UK HM Treasury consolidated sanctions list.

Public CSV at https://ofsistorage.blob.core.windows.net/publishlive/2022format/ConList.csv
(format has shifted over time; env override UK_HMT_SANCTIONS_URL supported).
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import os
from datetime import datetime, timezone

import httpx


logger = logging.getLogger(__name__)

DEFAULT_URL = "https://ofsistorage.blob.core.windows.net/publishlive/2022format/ConList.csv"


def fetch_recent(*, prior_ids: set[str] | None = None, timeout: float = 30.0) -> list[dict]:
    url = os.getenv("UK_HMT_SANCTIONS_URL", DEFAULT_URL)
    try:
        with httpx.Client(timeout=timeout) as c:
            resp = c.get(url)
            resp.raise_for_status()
            text = resp.text
    except Exception as e:
        logger.warning("uk_hmt_fetch_failed err=%s", e)
        return []

    reader = csv.DictReader(io.StringIO(text))
    articles: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for row in reader:
        group_id = row.get("Group ID") or row.get("GroupID") or ""
        if not group_id:
            continue
        if prior_ids is not None and group_id in prior_ids:
            continue

        name_parts = [row.get(k, "").strip() for k in ("Name 6", "Name 1", "Name 2", "Name 3", "Name 4", "Name 5")]
        name = " ".join(p for p in name_parts if p)
        regime = row.get("Regime") or row.get("Current Owners") or ""

        title = f"[UK HMT sanctions added] {name} — {regime}".strip(" —")
        url_detail = f"https://www.gov.uk/government/publications/the-uk-sanctions-list#group-{group_id}"
        content_hash = hashlib.md5(f"uk_hmt_{group_id}".encode()).hexdigest()

        articles.append({
            "content_hash": content_hash,
            "title": title[:500],
            "summary": title,
            "text": title,
            "url": url_detail,
            "source": "uk_hmt_sanctions",
            "source_kind": "sanctions",
            "published_at": now,
            "language": "en",
            "raw": {"group_id": group_id, "regime": regime},
        })

    logger.info("uk_hmt_delta articles=%d", len(articles))
    return articles
