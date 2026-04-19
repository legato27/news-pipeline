"""Canonical actor resolution.

Maps NER spans (PERSON/ORG/GPE/LOC/NORP) to canonical `Actor.id` keys like
"country:RU", "org:NATO", "person:Putin,Vladimir". Wikidata QID lookup is
optional (cached in `osint_actors.wikidata_qid`).

Phase 6 minimal impl: built-in country + IGO dictionary for GPE/NORP entities;
everything else is left as a free-text actor under kind=org/person/other and
resolved lazily the next time it appears.
"""
from __future__ import annotations

import re


# ISO 3166-1 alpha-2 name → country_code (non-exhaustive, the important ones for OSINT)
COUNTRY_NAME_TO_CODE: dict[str, str] = {
    "united states": "US", "usa": "US", "america": "US",
    "russia": "RU", "russian federation": "RU",
    "china": "CN", "prc": "CN",
    "ukraine": "UA",
    "israel": "IL",
    "iran": "IR",
    "north korea": "KP", "dprk": "KP",
    "south korea": "KR", "rok": "KR",
    "japan": "JP",
    "germany": "DE",
    "france": "FR",
    "uk": "GB", "united kingdom": "GB", "britain": "GB", "england": "GB",
    "india": "IN",
    "pakistan": "PK",
    "turkey": "TR", "türkiye": "TR",
    "syria": "SY",
    "yemen": "YE",
    "lebanon": "LB",
    "gaza": "PS", "palestine": "PS", "west bank": "PS",
    "saudi arabia": "SA",
    "iraq": "IQ",
    "afghanistan": "AF",
    "taiwan": "TW",
    "venezuela": "VE",
    "cuba": "CU",
    "belarus": "BY",
    "sudan": "SD",
    "libya": "LY",
    "ethiopia": "ET",
    "somalia": "SO",
    "nigeria": "NG",
    "myanmar": "MM", "burma": "MM",
}

# International orgs / known groups
KNOWN_ORG_IDS: dict[str, str] = {
    "nato": "org:NATO",
    "european union": "org:EU", "eu": "org:EU",
    "united nations": "org:UN", "un": "org:UN", "unsc": "org:UN-SC",
    "imf": "org:IMF",
    "world bank": "org:WorldBank",
    "who": "org:WHO", "world health organization": "org:WHO",
    "ocha": "org:OCHA",
    "hamas": "group:Hamas",
    "hezbollah": "group:Hezbollah",
    "houthi": "group:Houthis", "houthis": "group:Houthis",
    "isis": "group:ISIS", "islamic state": "group:ISIS",
    "taliban": "group:Taliban",
    "wagner": "group:WagnerGroup",
    "opec": "org:OPEC",
}


def resolve(entity_text: str, label: str) -> tuple[str, str, str]:
    """Resolve an NER entity to (actor_id, kind, canonical_name).

    Returns a sensible default if nothing matches. Actor rows should be upserted
    by the caller using the returned tuple.
    """
    t = entity_text.strip()
    tl = t.lower()

    # Countries (GPE or NORP labels carry nationality; GPE is strongest)
    if label in ("GPE", "LOC"):
        if tl in COUNTRY_NAME_TO_CODE:
            code = COUNTRY_NAME_TO_CODE[tl]
            return f"country:{code}", "country", t
        return f"location:{_slug(t)}", "other", t

    if label == "NORP":
        if tl in COUNTRY_NAME_TO_CODE:
            code = COUNTRY_NAME_TO_CODE[tl]
            return f"country:{code}", "country", t
        return f"group:{_slug(t)}", "group", t

    if label == "ORG":
        if tl in KNOWN_ORG_IDS:
            oid = KNOWN_ORG_IDS[tl]
            return oid, oid.split(":", 1)[0], t
        return f"org:{_slug(t)}", "org", t

    if label == "PERSON":
        return f"person:{_slug(t)}", "person", t

    return f"other:{_slug(t)}", "other", t


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip()).strip("_")
    return s[:120]
