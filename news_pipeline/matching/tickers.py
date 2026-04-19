"""Ticker matching — strict, watchlist-driven.

Extracted from Project-StockPrediction/.../services/sentiment/rss_crawler.match_tickers.
Preserves the five-strategy match hierarchy: crypto aliases, cashtag, short-ticker
(company-name-only), whole-word ticker, company name.
"""
from __future__ import annotations

import re


# Map crypto tickers to keyword aliases for better matching
# Covers both yfinance (BTC-USD) and ETF (BTC) formats
CRYPTO_ALIASES: dict[str, list[str]] = {
    "BTC-USD": ["bitcoin", "btc"],
    "ETH-USD": ["ethereum", "eth", "ether"],
    "SOL-USD": ["solana"],
    "XRP-USD": ["xrp", "ripple"],
    "ADA-USD": ["cardano", "ada"],
    "DOGE-USD": ["dogecoin", "doge"],
    "DOT-USD": ["polkadot"],
    "AVAX-USD": ["avalanche", "avax"],
    "LINK-USD": ["chainlink"],
    "MATIC-USD": ["polygon", "matic"],
    "UNI-USD": ["uniswap"],
    "ATOM-USD": ["cosmos", "atom"],
    "LTC-USD": ["litecoin", "ltc"],
    "BCH-USD": ["bitcoin cash", "bch"],
    "NEAR-USD": ["near protocol", "near"],
    "SUI-USD": ["sui"],
    "ARB-USD": ["arbitrum"],
    "OP-USD": ["optimism"],
    "APT-USD": ["aptos"],
    "FIL-USD": ["filecoin"],
    "PEPE-USD": ["pepe"],
    "SHIB-USD": ["shiba inu", "shib"],
    "AAVE-USD": ["aave"],
    "MKR-USD": ["maker", "makerdao"],
    "INJ-USD": ["injective"],
    "TIA-USD": ["celestia"],
    "SEI-USD": ["sei"],
    "STX-USD": ["stacks"],
    "HBAR-USD": ["hedera", "hbar"],
    "TRX-USD": ["tron", "trx"],
    "TON-USD": ["toncoin", "ton"],
    "RENDER-USD": ["render"],
    "XLM-USD": ["stellar", "xlm"],
    "ALGO-USD": ["algorand"],
    "FTM-USD": ["fantom"],
    "BTC": ["bitcoin", "btc", "grayscale bitcoin"],
    "XRP": ["xrp", "ripple"],
}

# Short tickers or common English words — require company name match ONLY
SHORT_TICKERS: set[str] = {
    "MA", "JD", "NOW", "ZS", "AI", "ON", "IT", "GO", "AM", "AN", "AA", "ED",
    "ALL", "ARE", "BIG", "CAN", "DAY", "HAS", "HE", "LOW", "MET", "NEW",
    "OUT", "RUN", "SAY", "SEE", "SO", "TWO", "WAR", "AAP", "GRAB",
}

_COMPANY_SUFFIXES = (
    " Inc.", " Inc", " Corp.", " Corp", " Ltd.", " Ltd",
    " Holdings", " Group", " Technologies", " Incorporated",
)


def match_tickers(
    article: dict,
    tickers: list[str],
    company_names: dict[str, str],
) -> list[str]:
    """Match article to watchlist tickers. Strict — must explicitly mention the asset.

    Strategies (first match wins):
      1. Crypto aliases (e.g., "Bitcoin" -> BTC-USD)
      2. $TICKER cashtag
      3. Short tickers (<=2 chars or in SHORT_TICKERS): require company name match
      4. Whole-word ticker match (3+ chars)
      5. Company name match
    """
    title = article.get("title", "")
    summary = article.get("summary", "")
    full_text = f"{title} {summary}"
    text_upper = full_text.upper()

    matched: list[str] = []

    for ticker in tickers:
        # 1. Crypto alias matching
        aliases = CRYPTO_ALIASES.get(ticker, [])
        if aliases:
            text_lower = full_text.lower()
            if any(alias in text_lower for alias in aliases):
                matched.append(ticker)
                continue

        # 2. Cashtag: $AAPL (always reliable)
        if f"${ticker}" in text_upper:
            matched.append(ticker)
            continue

        # 3. Short tickers: require cashtag or company name only
        if ticker in SHORT_TICKERS or len(ticker) <= 2:
            name = company_names.get(ticker, "")
            if name and len(name) > 3:
                pattern = re.compile(r'\b' + re.escape(name) + r'\b', re.IGNORECASE)
                if pattern.search(full_text):
                    matched.append(ticker)
            continue

        # 4. Standard ticker: whole-word match (3+ chars)
        ticker_pattern = re.compile(r'\b' + re.escape(ticker) + r'\b')
        if ticker_pattern.search(text_upper):
            matched.append(ticker)
            continue

        # 5. Company name match
        name = company_names.get(ticker, "")
        if name and len(name) > 3:
            match_name = name.split(",")[0].strip()
            for suffix in _COMPANY_SUFFIXES:
                match_name = match_name.replace(suffix, "")
            match_name = match_name.strip()

            if len(match_name) >= 4:
                pattern = re.compile(r'\b' + re.escape(match_name) + r'\b', re.IGNORECASE)
                if pattern.search(full_text):
                    matched.append(ticker)

    return matched
