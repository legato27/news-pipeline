# news-pipeline

Shared news + sentiment library consumed by `polymarket-agent` and `Project-StockPrediction`.

## Install (editable, from each consumer app's venv)

```
pip install -e /home/legato/custom-apps/news-pipeline
```

No changes required to the consumer apps' `pyproject.toml`. Their existing import sites are preserved via shim modules that re-export from `news_pipeline.*`.

## Layout

```
news_pipeline/
  schema.py          # Article, SentimentScore, SocialPost, RedditMeta (Pydantic v2)
  ingest/            # RSS, Finnhub, NewsAPI
  social/            # Reddit (PRAW + public JSON), StockTwits, Finnhub social
  matching/          # tickers, categories, language
  scoring/           # VADER, FinBERT (local in Phase 1; DGX-hosted in Phase 2), Ollama LLM, composite
```

Phase 1 keeps FinBERT local. Phase 2 routes inference through DGX at `spark-dgx:30200/v1/score/finbert` via `scoring/client.py`.
