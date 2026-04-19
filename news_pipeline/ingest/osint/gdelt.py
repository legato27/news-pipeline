"""GDELT 2.0 ingest — global event & news mentions.

GDELT publishes a CSV of events every 15 minutes at:
  http://data.gdeltproject.org/gdeltv2/lastupdate.txt

Three files per cycle:
  - events.CSV.zip   — structured CAMEO events (actor1, actor2, eventcode, lat, lon, tone)
  - mentions.CSV.zip — article-level mentions of those events
  - gkg.csv.zip      — Global Knowledge Graph (themes, entities, locations)

For Phase 5 we land raw events as osint_articles with source_kind='gdelt' and
preserve the CAMEO/event fields in `raw` for Phase 6 event extraction.
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import zipfile
from datetime import datetime, timezone

import httpx


logger = logging.getLogger(__name__)

LASTUPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"

# GDELT 2.0 event schema: 61 columns. See:
# http://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf
EVENT_COLUMNS = [
    "GlobalEventID", "Day", "MonthYear", "Year", "FractionDate",
    "Actor1Code", "Actor1Name", "Actor1CountryCode", "Actor1KnownGroupCode",
    "Actor1EthnicCode", "Actor1Religion1Code", "Actor1Religion2Code",
    "Actor1Type1Code", "Actor1Type2Code", "Actor1Type3Code",
    "Actor2Code", "Actor2Name", "Actor2CountryCode", "Actor2KnownGroupCode",
    "Actor2EthnicCode", "Actor2Religion1Code", "Actor2Religion2Code",
    "Actor2Type1Code", "Actor2Type2Code", "Actor2Type3Code",
    "IsRootEvent", "EventCode", "EventBaseCode", "EventRootCode",
    "QuadClass", "GoldsteinScale",
    "NumMentions", "NumSources", "NumArticles", "AvgTone",
    "Actor1Geo_Type", "Actor1Geo_FullName", "Actor1Geo_CountryCode",
    "Actor1Geo_ADM1Code", "Actor1Geo_ADM2Code", "Actor1Geo_Lat", "Actor1Geo_Long", "Actor1Geo_FeatureID",
    "Actor2Geo_Type", "Actor2Geo_FullName", "Actor2Geo_CountryCode",
    "Actor2Geo_ADM1Code", "Actor2Geo_ADM2Code", "Actor2Geo_Lat", "Actor2Geo_Long", "Actor2Geo_FeatureID",
    "ActionGeo_Type", "ActionGeo_FullName", "ActionGeo_CountryCode",
    "ActionGeo_ADM1Code", "ActionGeo_ADM2Code", "ActionGeo_Lat", "ActionGeo_Long", "ActionGeo_FeatureID",
    "DATEADDED", "SOURCEURL",
]


def _fetch_latest_urls(timeout: float = 15.0) -> dict[str, str]:
    """Parse lastupdate.txt → dict with keys 'export' (events), 'mentions', 'gkg'."""
    with httpx.Client(timeout=timeout) as c:
        resp = c.get(LASTUPDATE_URL)
        resp.raise_for_status()

    urls: dict[str, str] = {}
    for line in resp.text.strip().splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        url = parts[2]
        if "export.CSV.zip" in url:
            urls["export"] = url
        elif "mentions.CSV.zip" in url:
            urls["mentions"] = url
        elif "gkg.csv.zip" in url:
            urls["gkg"] = url
    return urls


def _download_csv_zip(url: str, *, timeout: float = 30.0) -> list[list[str]]:
    """Download a zipped CSV, extract, return rows as lists."""
    with httpx.Client(timeout=timeout) as c:
        resp = c.get(url)
        resp.raise_for_status()
        data = resp.content

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        name = zf.namelist()[0]
        with zf.open(name) as f:
            text = f.read().decode("utf-8", errors="replace")

    return list(csv.reader(io.StringIO(text), delimiter="\t"))


def fetch_recent(*, limit: int = 500) -> list[dict]:
    """Fetch the latest GDELT 2.0 events, return as Article-compatible dicts.

    Only events whose SOURCEURL is a news article URL are kept; raw CAMEO fields
    land in `raw` so Phase 6 can build OsintEvent rows with location + actors.
    """
    try:
        urls = _fetch_latest_urls()
    except Exception as e:
        logger.warning("gdelt_lastupdate_failed err=%s", e)
        return []

    if "export" not in urls:
        return []

    try:
        rows = _download_csv_zip(urls["export"])
    except Exception as e:
        logger.warning("gdelt_events_download_failed err=%s", e)
        return []

    articles: list[dict] = []
    seen: set[str] = set()

    for row in rows[:limit]:
        if len(row) < len(EVENT_COLUMNS):
            continue
        rec = dict(zip(EVENT_COLUMNS, row))

        url = rec.get("SOURCEURL", "").strip()
        if not url:
            continue

        # Build a pseudo-title from actors + event code (real title arrives via mentions)
        a1 = rec.get("Actor1Name") or rec.get("Actor1Code") or ""
        a2 = rec.get("Actor2Name") or rec.get("Actor2Code") or ""
        geo = rec.get("ActionGeo_FullName", "")
        ec = rec.get("EventCode", "")
        title = f"[GDELT {ec}] {a1} → {a2} ({geo})".strip()

        try:
            day = rec.get("Day", "")
            pub_dt = datetime.strptime(day, "%Y%m%d").replace(tzinfo=timezone.utc) if day else datetime.now(timezone.utc)
        except Exception:
            pub_dt = datetime.now(timezone.utc)

        content_hash = hashlib.md5(f"gdelt_{rec.get('GlobalEventID', '')}{url}".encode()).hexdigest()
        if content_hash in seen:
            continue
        seen.add(content_hash)

        articles.append({
            "content_hash": content_hash,
            "title": title[:300],
            "summary": f"CAMEO {ec} (quad={rec.get('QuadClass')}, goldstein={rec.get('GoldsteinScale')}, tone={rec.get('AvgTone')})",
            "text": title,
            "url": url,
            "source": "gdelt",
            "source_kind": "gdelt",
            "published_at": pub_dt.isoformat(),
            "language": "en",
            "raw": rec,
        })

    logger.info("gdelt_crawl_complete events=%d", len(articles))
    return articles
