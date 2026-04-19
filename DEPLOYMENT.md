# News-Pipeline Deployment Punch List

Eight phases were written, covering standardization of sentiment pipelines plus a full OSINT build-out. Code is landed; several phases require infrastructure steps before they run.

## What's done (code)

| Phase | Artifact | Status |
|---|---|---|
| 1 | `news-pipeline/` shared package (schema, ingest, social, matching, scoring) | ✅ Verified import |
| 1 | polymarket-agent shims + StockPrediction shims | ✅ Verified import |
| 2 | `stock-research-app/inference/` FastAPI (FinBERT, LLM, embed, NER, translate, classify) + Dockerfile | ✅ Code landed |
| 2 | `news_pipeline.scoring.client.InferenceClient` (batched, retry, VADER fallback) | ✅ Verified |
| 2 | Celery loop batched (`sentiment_tasks.crawl_watchlist_sentiment`) | ✅ Code landed |
| 2 | Alembic 008 — `content_hash` column on `sentiment_cache` | ✅ Code landed |
| 3 | `docker-compose.cloud.yml` + `docker-compose.dgx.yml` (slimmed) + `cloud/db/Dockerfile` (pgvector + PostGIS) | ✅ Code landed |
| 3 | Alembic 009 — enable `vector` + `postgis` extensions | ✅ Code landed |
| 4 | Cloud routes added: `/api/sentiment/category/{name}`, `/.../windows`, `/ticker-buzz/{ticker}`, `/finnhub/{category}` | ✅ Code landed |
| 4 | polymarket `sentiment/api.py` retired to a stub that raises | ✅ Code landed |
| 5 | OSINT ingest — GDELT, ACLED, ReliefWeb, CISA KEV+advisories, OTX, MISP, vendor RSS, OFAC/EU/UK/UN/SEC sanctions, geopolitical RSS (25 feeds) | ✅ Code landed |
| 5 | OSINT social — Telegram (t.me scrape), Bluesky (public search), Mastodon (public timelines) | ✅ Code landed |
| 5 | OSINT DB models + Alembic 010 (pgvector + PostGIS columns, HNSW + GIST indexes) | ✅ Code landed |
| 5 | OSINT Celery tasks + Beat schedule (8 new tasks on `osint` queue) | ✅ Code landed |
| 6 | OSINT processing pipeline (translate → NER → geolocate → embed → dedup → classify → event) | ✅ Code landed |
| 7 | OSINT API routes (`/api/osint/{events,timeline,map,actors,indices,articles}`) + router registration | ✅ Code landed |
| 7 | vibefin Next.js pages — `/osint`, `/osint/map`, `/osint/timeline`, `/osint/indices`, `/osint/actors/[id]` | ✅ Code landed |
| 7 | Folded `source_kind=osint` filter into `/api/sentiment/news-feed` | ✅ Code landed |
| 8 | `osint_indices_timeseries` table + Alembic 011 + compute task (hourly) | ✅ Code landed |
| 8 | `services/forecast_osint.py` — ticker→region exposure map + feature extractor | ✅ Code landed |

## Deployment steps (required before running)

1. **Install `news-pipeline` into each consumer venv/image:**
   - Cloud api + worker + scheduler: already wired in `docker-compose.cloud.yml` via `pip install -e /news-pipeline -e . -q` in the `command`.
   - polymarket-agent: run `pip install -e /home/legato/custom-apps/news-pipeline` in its venv.
   - (Hook blocks pip here — run locally.)

2. **Build the DGX inference image:**
   ```
   cd /home/legato/custom-apps/Project-StockPrediction/stock-research-app/inference
   docker build -t news-inference:0.1 .
   ```

3. **Pull Ollama qwen3.5 on DGX:**
   ```
   docker exec ollama ollama pull qwen3.5
   ```

4. **Run Alembic migrations against cloud Postgres:**
   ```
   cd .../stock-research-app/backend
   alembic upgrade head   # 008 → 009 → 010 → 011
   ```
   Migration 009 enables `vector` + `postgis`; 010 creates OSINT tables; 011 creates the indices time-series table.

5. **Set env vars on the cloud .env:**
   ```
   NEWS_PIPELINE_INFERENCE_URL=http://spark-dgx:30200
   NEWS_PIPELINE_INFERENCE_TOKEN=<shared bearer>
   # Optional OSINT sources
   ACLED_API_KEY=...
   ACLED_EMAIL=...
   OTX_API_KEY=...
   MISP_BASE_URL=...
   MISP_API_KEY=...
   EU_SANCTIONS_URL=...
   UK_HMT_SANCTIONS_URL=...  # defaults to public URL if unset
   TELEGRAM_CHANNELS=...     # comma-separated (optional; defaults to OSINT list)
   BLUESKY_QUERIES=...
   MASTODON_INSTANCES=...
   ```

6. **Set the same bearer on DGX .env:**
   ```
   NEWS_PIPELINE_INFERENCE_TOKEN=<shared bearer>
   ```

7. **Bring up the two sides:**
   ```
   # DGX (brain)
   docker-compose -f docker-compose.dgx.yml up -d

   # Cloud (fin.vibelife.sg)
   docker-compose -f docker-compose.cloud.yml up -d
   ```

8. **Add an `osint` queue worker** (included in `docker-compose.cloud.yml`'s worker command: `-Q default,watchlist,models,osint`). Verify with `celery -A app.tasks.celery_app inspect active_queues`.

## Per-phase verification

**Phase 1** — both apps' existing smoke flows produce within-20% article counts.
Already verified via import tests: polymarket's `sentiment.api` loads with 6 routes; SP shims export all consumer-required symbols.

**Phase 2**
- `curl -X POST spark-dgx:30200/v1/score/finbert -d '{"texts":["Apple smashed estimates"]}'` matches local `_finbert_score`.
- Stop DGX inference service → Celery task still completes (VADER fallback).
- Locally smoke-tested: `score_finbert_batch_compound([...])` returns scores.

**Phase 3**
- `docker exec dgx-<any> netstat -an | grep :5432` → empty (no DB on DGX).
- `docker exec cloud-db psql -U stockuser -c "SELECT extname FROM pg_extension WHERE extname IN ('vector','postgis')"` → both rows.

**Phase 4**
- `curl https://fin.vibelife.sg/api/sentiment/category/btc_milestones?window=60` returns payload matching legacy polymarket :8001 shape (category/score/buzz/direction/confidence/article_count/key_headline/window_minutes).
- `curl https://fin.vibelife.sg/api/sentiment/ticker-buzz/NVDA` returns buzz dict.
- `uvicorn sentiment.api:app` (polymarket) raises RuntimeError.

**Phase 5**
```
SELECT source_kind, COUNT(*) FROM osint_articles
WHERE fetched_at > now() - interval '2 hours' GROUP BY 1;
```
Should show non-zero rows for `gdelt`, `osint_rss`, `reliefweb`, `cisa`, `sanctions` within a couple of cycles.

**Phase 6**
- `SELECT COUNT(*) FROM osint_events WHERE created_at > now() - interval '30 minutes';` > 0.
- Insert a non-English GDELT article, confirm `translated_text IS NOT NULL` after one `process_pending` cycle.
- Same event from 3 sources clusters to a single `event_id` with 3 rows in `osint_event_articles`.
- Stop DGX → pipeline still lands articles with empty actors/event and does not raise.

**Phase 7**
- `curl https://fin.vibelife.sg/api/osint/events?urgency=high&since_hours=24` returns array.
- `curl https://fin.vibelife.sg/api/osint/map?since_hours=24` returns valid GeoJSON.
- Browser visit `https://fin.vibelife.sg/osint` loads feed page with filters.
- `curl '.../api/sentiment/news-feed?source_kind=gdelt'` returns OSINT articles only.

**Phase 8**
- `SELECT index_name, region, value FROM osint_indices_timeseries ORDER BY ts DESC LIMIT 10;` shows rising values.
- `python -c "from app.services.forecast_osint import compute_ticker_osint_features; print(compute_ticker_osint_features('LMT'))"` returns non-zero `osint_geopolitical_risk`.

## Known placeholders / follow-ups

- **vibefin map page** uses a simple SVG grid placeholder. For production swap to react-leaflet or mapbox-gl (GeoJSON payload is already in the right shape).
- **Event summarization** (Phase 6) currently uses first 500 chars of title/translation. LLM-synthesized 1-2 sentence summaries from clustered articles are not wired — add a per-new-event `client.score_llm` call in `osint/pipeline.py` when you want richer summaries.
- **MISP/OTX/ACLED** ingests require API keys. They're gated on env presence and return `[]` gracefully when missing.
- **Telegram** uses t.me web scrape. For production conflict OSINT, move to Telethon (MTProto) with `TELEGRAM_API_ID` + `TELEGRAM_API_HASH`.
- **GeoNames gazetteer** is not shipped; `matching/geo.py` uses a minimal country-centroid map. Attach a GeoNames dump for city-level resolution.
- **Ticker → OSINT region map** (`TICKER_OSINT_EXPOSURE` in `forecast_osint.py`) covers ~15 tickers explicitly. Extend from SIC codes / sector lookups.
- **DGX ↔ cloud authentication** uses a shared bearer token. For stronger guarantees, swap to mTLS with client certs pinned via Tailscale ACLs.

## Rollback plan

Each phase is reversible:
- Phase 1: revert the shim files; `news-pipeline` package is harmless if left installed.
- Phase 2: unset `NEWS_PIPELINE_INFERENCE_URL` → client disables, cloud reverts to local FinBERT.
- Phase 3: stop the new compose files, restart the original `docker-compose.dgx.yml` from git.
- Phase 4: un-retire `sentiment/api.py` from git history.
- Phase 5-8: `alembic downgrade 007` drops all OSINT tables; stop the OSINT worker/scheduler; delete `osint_tasks.py` from the Celery include list.
