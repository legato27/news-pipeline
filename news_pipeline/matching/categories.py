"""Market/topic categories + keyword matching.

Extracted from polymarket-agent/config/categories.py so both apps (and Phase 5 OSINT)
can share the same CATEGORIES taxonomy. Phase 5 will add OSINT-specific categories
(armed_conflict, cyber_advisory, sanctions_change, etc.) here.
"""
from __future__ import annotations


CATEGORIES: dict[str, dict] = {
    "politics_us": {
        "keywords": [
            "trump", "biden", "president", "congress", "senate", "democrat",
            "republican", "white house", "executive order", "impeach",
            "governor", "election", "electoral", "gop", "dnc", "rnc",
            "speaker of the house", "vice president", "cabinet",
        ],
        "description": "US politics and government",
    },
    "politics_world": {
        "keywords": [
            "prime minister", "parliament", "election", "president of",
            "chancellor", "regime", "coup", "resign", "nato", "eu ",
            "european union", "xi jinping", "modi", "macron", "starmer",
            "orban", "magyar", "zelensky", "putin",
        ],
        "description": "International politics and elections",
    },
    "geopolitics": {
        "keywords": [
            "war", "military", "invasion", "iran", "israel", "ukraine",
            "russia", "china", "taiwan", "north korea", "sanctions",
            "missile", "nuclear", "conflict", "ceasefire", "peace deal",
            "strait of hormuz", "kharg island", "houthi", "hezbollah",
            "hamas", "troops", "bomb", "strike", "attack",
        ],
        "description": "Geopolitical conflicts and international relations",
    },
    "crypto": {
        "keywords": [
            "bitcoin", "btc", "ethereum", "eth", "crypto", "solana",
            "sol", "defi", "stablecoin", "blockchain", "altcoin",
            "binance", "coinbase", "halving", "etf",
        ],
        "description": "Cryptocurrency and blockchain markets",
    },
    "economics": {
        "keywords": [
            "fed ", "fomc", "interest rate", "federal reserve", "rate cut",
            "rate hike", "monetary policy", "inflation", "cpi", "gdp",
            "recession", "unemployment", "tariff", "trade war", "s&p",
            "nasdaq", "dow jones", "stock market", "treasury", "bond",
            "debt ceiling",
        ],
        "description": "Economics, central banks, and financial markets",
    },
    "tech": {
        "keywords": [
            "ai model", "openai", "anthropic", "google ai", "chatgpt",
            "claude", "gemini", "llm", "artificial intelligence", "gpt",
            "apple", "microsoft", "meta", "nvidia", "tesla", "spacex",
            "launch", "starship", "ipo", "acquisition", "merger",
        ],
        "description": "Technology, AI, and corporate events",
    },
    "sports": {
        "keywords": [
            " vs ", " vs. ", "nba", "nfl", "mlb", "nhl", "ufc", "pga",
            "masters", "world cup", "champions league", "la liga",
            "premier league", "super bowl", "playoffs", "finals",
            "match", "game", "tournament", "grand slam", "wimbledon",
            "olympic", "heavyweight", "title fight",
        ],
        "description": "Sports outcomes",
    },
    "science_health": {
        "keywords": [
            "covid", "pandemic", "vaccine", "fda", "drug", "clinical trial",
            "who ", "disease", "outbreak", "earthquake", "hurricane",
            "climate", "temperature", "nasa", "asteroid",
        ],
        "description": "Science, health, and natural events",
    },
    "entertainment": {
        "keywords": [
            "oscar", "grammy", "emmy", "box office", "movie", "album",
            "netflix", "streaming", "celebrity", "award",
        ],
        "description": "Entertainment and pop culture",
    },
    "other": {
        "keywords": [],
        "description": "Uncategorized markets",
    },
}

CLAUDE_STRONG_CATEGORIES: list[str] = [
    "politics_us", "politics_world", "geopolitics",
    "economics", "tech", "crypto",
]


def classify_market(question: str, description: str = "") -> str:
    """Classify a market into a category based on keyword matching."""
    text = (question + " " + description).lower()

    for category, config in CATEGORIES.items():
        if category == "other":
            continue
        if any(kw in text for kw in config["keywords"]):
            return category

    return "other"
