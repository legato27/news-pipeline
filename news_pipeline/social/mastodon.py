"""Mastodon public timeline ingest.

Pulls the federated 'public' timeline from configured instance(s). Works without
auth for public timelines.

Env: MASTODON_INSTANCES (comma-separated hostnames), defaults to mastodon.social.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re

import httpx


logger = logging.getLogger(__name__)

DEFAULT_INSTANCES: list[str] = ["mastodon.social", "infosec.exchange"]


def _fetch_timeline(instance: str, *, limit: int = 40, timeout: float = 15.0) -> list[dict]:
    url = f"https://{instance}/api/v1/timelines/public"
    try:
        with httpx.Client(timeout=timeout) as c:
            resp = c.get(url, params={"limit": limit, "local": "false"})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning("mastodon_fetch_failed instance=%s err=%s", instance, e)
        return []


def fetch_recent(*, instances: list[str] | None = None) -> list[dict]:
    env_inst = os.getenv("MASTODON_INSTANCES", "")
    if env_inst:
        instances = [i.strip() for i in env_inst.split(",") if i.strip()]
    instances = instances or DEFAULT_INSTANCES

    all_posts: list[dict] = []
    seen: set[str] = set()

    for inst in instances:
        for status in _fetch_timeline(inst):
            sid = status.get("id", "")
            if not sid:
                continue
            content_html = status.get("content", "")
            text = re.sub(r"<[^>]+>", " ", content_html).strip()
            text = re.sub(r"\s+", " ", text)
            if not text:
                continue

            url = status.get("url", "")
            account = status.get("account", {})
            acct = account.get("acct", "")
            content_hash = hashlib.md5(f"mastodon_{inst}_{sid}".encode()).hexdigest()
            if content_hash in seen:
                continue
            seen.add(content_hash)

            all_posts.append({
                "content_hash": content_hash,
                "title": text[:200],
                "text": text[:2000],
                "summary": text[:500],
                "url": url,
                "source": f"mastodon_{inst}_{acct}" if acct else f"mastodon_{inst}",
                "source_kind": "mastodon",
                "published_at": status.get("created_at"),
                "language": status.get("language") or "auto",
                "raw": {
                    "instance": inst,
                    "status_id": sid,
                    "favourites_count": status.get("favourites_count", 0),
                    "reblogs_count": status.get("reblogs_count", 0),
                },
            })

    logger.info("mastodon_crawl_complete posts=%d", len(all_posts))
    return all_posts
