"""OFAC (US Treasury) Specially Designated Nationals (SDN) delta watcher.

OFAC publishes the SDN list as CSV + XML at:
  https://www.treasury.gov/ofac/downloads/sdn.csv
  https://www.treasury.gov/ofac/downloads/sdn_advanced.xml

Strategy: snapshot the CSV each run. Emit Article-compatible records for rows
whose ent_num was not present in the prior snapshot. Prior snapshot is passed
by the caller (usually read from storage/osint_snapshots table).
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
from datetime import datetime, timezone

import httpx


logger = logging.getLogger(__name__)

SDN_CSV_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"

# OFAC SDN CSV columns per their documentation:
# ent_num,SDN_Name,SDN_Type,Program,Title,Call_Sign,Vess_type,Tonnage,GRT,Vess_flag,Vess_owner,Remarks
SDN_COLUMNS = [
    "ent_num", "SDN_Name", "SDN_Type", "Program", "Title",
    "Call_Sign", "Vess_type", "Tonnage", "GRT", "Vess_flag",
    "Vess_owner", "Remarks",
]


def fetch_snapshot(*, timeout: float = 30.0) -> list[dict]:
    """Return full SDN list as a list of dicts (one per row)."""
    try:
        with httpx.Client(timeout=timeout) as c:
            resp = c.get(SDN_CSV_URL)
            resp.raise_for_status()
            text = resp.text
    except Exception as e:
        logger.warning("ofac_sdn_download_failed err=%s", e)
        return []

    rows = list(csv.reader(io.StringIO(text)))
    out: list[dict] = []
    for row in rows:
        if len(row) < len(SDN_COLUMNS):
            continue
        rec = dict(zip(SDN_COLUMNS, row))
        if rec["ent_num"].strip().isdigit():
            out.append(rec)
    return out


def fetch_recent(*, prior_ent_nums: set[str] | None = None) -> list[dict]:
    """Return only rows added since prior_ent_nums (set of SDN ent_num strings).

    If prior_ent_nums is None, the caller gets the full list tagged as additions
    (useful for the initial ingest).
    """
    snapshot = fetch_snapshot()
    new_rows = [
        r for r in snapshot
        if prior_ent_nums is None or r["ent_num"] not in prior_ent_nums
    ]

    articles: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for r in new_rows:
        ent = r["ent_num"]
        name = r["SDN_Name"].strip()
        program = r["Program"]
        sdn_type = r["SDN_Type"]
        remarks = r["Remarks"].strip('"').strip()

        title = f"[OFAC SDN added] {name} — {program}"
        url = f"https://sanctionssearch.ofac.treas.gov/Details.aspx?id={ent}"
        content_hash = hashlib.md5(f"ofac_sdn_{ent}".encode()).hexdigest()

        articles.append({
            "content_hash": content_hash,
            "title": title[:500],
            "summary": remarks[:500],
            "text": f"{title}. {remarks[:300]}",
            "url": url,
            "source": "ofac_sdn",
            "source_kind": "sanctions",
            "published_at": now,
            "language": "en",
            "raw": {
                "ent_num": ent,
                "sdn_type": sdn_type,
                "program": program,
                "title": r.get("Title"),
                "remarks": remarks,
            },
        })

    logger.info("ofac_sdn_delta articles=%d (prior_known=%s)",
                len(articles), "yes" if prior_ent_nums else "no")
    return articles
