# Asia-Pacific Tech Gateway

Asia-Pacific Tech Gateway (APTG) is a beta discovery service for searching
technology offers and transfer or licensing listings from publicly accessible source platforms
across Asia and the Pacific. It helps users discover relevant records in one
place and then sends them to the original provider for authoritative details
and follow-up.

APTG does not generally store the underlying technology documents. Searchable
metadata is obtained through public APIs, public Drupal exports, or periodically
reviewed crawler snapshots. Inclusion of a source does not imply a partnership,
endorsement, or responsibility by the source institution for APTG. Records in
the APCTT Technology Offers catalogue are submitted directly to APCTT; APCTT may
review them and, where appropriate, support coordination with the submitter.

The service is currently in beta. Product, attribution, legal, and operational
arrangements may change following formal review.

## How it works

- Searches registered metadata sources concurrently.
- Merges results using round-robin pagination so one large source does not
  dominate the first page.
- Applies country, sector, database-type, and source filters in real time.
- Uses query-aware facet counts for locally indexed catalogues.
- Links each result to its original source record.
- Falls back safely when an optional live source or semantic-search service is
  unavailable.

Technology sectors use an ISO ICS-based shared vocabulary. The internal model
supports all 40 ISO ICS top-level fields. Provider categories are preserved in
`source_sector`; normalized classifications are stored in `sector_codes`,
`sector_labels`, `classification_method`, and `classification_confidence`.
Numeric ICS codes are used internally but the interface displays sector names.
Uncertain or unmapped records remain searchable as `Other / Unclassified`.
This is an ISO ICS-based vocabulary, not an ISO certification.

## Data sources

| Source | Coverage | Integration |
|---|---|---|
| Korea National Technology Bank | Republic of Korea | Live public API; enabled when `KOREA_NTB_API_KEY` is configured |
| WIPO PATENTSCOPE | International | Redirects to WIPO search with the user's query |
| CSIR India Technology Portal | India | Reviewed crawler snapshot stored as JSON |
| DOST-TAPI | Philippines | Reviewed crawler snapshot stored as JSON |
| Tech2Biz | Thailand | Reviewed crawler snapshot stored as JSON |
| JST Japan Patent Portfolio | Japan | Reviewed crawler snapshot stored as JSON |
| NRDC India | India | Reviewed crawler snapshot stored as JSON |
| ITI Technology Bank | Sri Lanka | Reviewed crawler snapshot stored as JSON |
| Malaysia R&D Commercialisation Portal | Malaysia | Reviewed public-catalogue snapshot stored as JSON; contact fields omitted |
| APCTT Technology Offers | Asia and the Pacific | Public Drupal REST Export with a bundled fallback snapshot |

Source websites remain authoritative. Crawled snapshots can lag behind their
providers and should be refreshed and reviewed before release. See
[`docs/crawling.md`](docs/crawling.md) for the current crawler inventory and
safe refresh procedure.

## Architecture

```text
frontend/
  index.html              Main search, sources, and About interface
  app.js                  Search, filters, facets, cards, and navigation
  styles.css              Responsive visual system
  privacy-notice.html     Privacy notice
  terms-of-use.html       Terms of use

backend/
  main.py                 FastAPI app and CORS configuration
  config.py               Environment-backed settings
  routers/
    search.py             Search endpoint
    sources.py            Source inventory and query-aware facets
    analytics.py          Privacy-preserving popular-topic counts
  middleware/             Rate limiting and security headers
  sources/
    base.py               Source interface
    registry.py           Active source registry
    static_json_source.py Shared loader/search implementation for snapshots
    data/*.json           Reviewed searchable snapshots
  taxonomy/               ISO ICS and provider-to-ICS mappings
  analytics/              Allow-listed aggregate topic counts
  search/                  Optional semantic and related-term search
  cache/                   SQLite-backed ephemeral caches

scripts/
  dev.sh                  Local frontend and backend launcher
  crawl_*.py              Manual crawler commands
  build_semantic_index.py Optional semantic-index builder
```

`scripts/crawl_slintec.py` is currently orphaned. Slintec is not registered as
an active source and no Slintec production index is included.

## API endpoints

The backend exposes:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Service health check |
| `GET` | `/api/v1/search` | Federated metadata search |
| `GET` | `/api/v1/sources` | Registered source metadata |
| `GET` | `/api/v1/facets` | Query- and filter-aware facets |
| `GET` | `/api/v1/popular-searches` | Ranked allow-listed topics for the previous 30 days |
| `POST` | `/api/v1/search-events` | Increment an allow-listed aggregate topic count |

Interactive FastAPI documentation is available at `/docs` on a running backend.

## Run locally

Python 3.11 or newer is required.

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
./scripts/dev.sh
```

On Windows, activate the environment with `.venv\Scripts\activate` and start
the frontend and backend separately using equivalent commands.

Open `http://127.0.0.1:5501`. The frontend uses
`http://127.0.0.1:8000/api/v1` when served from localhost and the deployed API
elsewhere.

For the same checks used in continuous integration, install the development
requirements and run:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --test tests/frontend-security.test.js tests/frontend-analytics.test.js tests/frontend-seo.test.js tests/merged-pagination.test.js
python scripts/validate_crawled_data.py
python -m pip_audit -r backend/requirements.txt
```

GitHub Actions repeats these checks on pushes and pull requests, performs a
monthly dependency audit, and checks the deployed API endpoints each day.

The bundled snapshots work without API credentials. To enable optional live or
semantic features, create an ignored `.env` file in the repository root:

```dotenv
KOREA_NTB_API_KEY=your_data_go_kr_key
KOREA_NTB_BASE_URL=https://apis.data.go.kr/B552536/tech_4/techall
KOREA_NTB_TTL_SECONDS=86400
CACHE_TTL_SECONDS=86400

GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_RELATED_TERMS_MODEL=gemini-3.5-flash-lite
SEMANTIC_SEARCH_ENABLED=true
SEMANTIC_SEARCH_MODEL=gemini-embedding-001
SEMANTIC_SEARCH_DIMENSIONS=768
SEMANTIC_SEARCH_DB_PATH=backend/cache/semantic_search.db
SEMANTIC_SEARCH_DAILY_QUERY_LIMIT=800

SEARCH_ANALYTICS_DB_PATH=backend/cache/search_analytics.db
```

Never commit `.env` or expose API keys in frontend code.

## Search analytics and semantic search

Popular searches retain only `topic_id`, date, and aggregate count for six
predefined topics. Arbitrary queries, IP addresses, and browser identifiers are
not stored. Searches outside the allow-list are ignored.

Semantic search is optional and fail-open. When Gemini is unavailable, the
daily quota is exhausted, or no document-vector index exists, search continues
with keyword matching and locally cached related terms. The configured default
limit is 800 Gemini query calls per Pacific-time day. Query-vector records use
a SHA-256 hash of the normalized query rather than the raw query.

Build or refresh the local semantic index after changing crawler data:

```sh
python scripts/build_semantic_index.py
python scripts/build_semantic_index.py --source csir_india
```

## Deployment

Production currently uses separate Render services for the static frontend and
FastAPI backend. The public frontend is available at
[`https://ap-tg.net`](https://ap-tg.net), while the frontend calls the backend
at `https://apsei-api.onrender.com/api/v1`.

`render.yaml` describes the backend service, but it is not the complete source
of truth for the existing frontend service or the settings configured in the
Render dashboard. Confirm build commands, environment variables, instance
type, and manual/automatic deployment settings in Render before changing them.
The currently configured backend build command reads the root
`requirements.txt`; keep it synchronized with `backend/requirements.txt` unless
the dashboard command is changed first.

The paid backend instance avoids free-tier inactivity spin-down. SQLite files
remain ephemeral unless their configured paths point to a persistent disk or
external database: data can still reset during replacement deployments,
service recreation, or other filesystem resets.

When deploying frontend changes, update the query versions attached to
`styles.css` and `app.js` in `frontend/index.html` so browsers do not continue
using stale assets. Do not document a fixed version number here; the HTML file
is the source of truth.

## Security and privacy

- Backend responses include CSP, HSTS, `X-Content-Type-Options`, frame,
  referrer, and permissions policies.
- The frontend defines a restrictive CSP in its HTML documents.
- Technology and source values are escaped before being rendered into cards.
- The public API is rate-limited and CORS is restricted to the deployed APTG,
  APCTT, and local development origins.
- External links open with `noopener noreferrer`.
- API keys are read only from backend environment variables.

The current CORS allow-list is defined in `backend/main.py`; update it when the
frontend domain changes. See [`docs/troubleshooting.md`](docs/troubleshooting.md)
for common local and deployment issues.

## Adding a source

For a live API, create `backend/sources/<name>.py`, subclass `BaseSource`,
implement `search()` and `is_healthy()`, and register it in
`backend/sources/registry.py`.

For a periodically crawled catalogue:

1. Add a crawler under `scripts/` that writes to a staging file by default.
2. Validate and review the snapshot before replacing production data.
3. Store the reviewed output under `backend/sources/data/`.
4. Subclass `StaticJSONSource` and register the source.
5. Preserve the provider category and add a reviewable mapping in
   `backend/taxonomy/iso_ics.py`.

Set `sector_filter_supported = True` only when the source mapping and filtered
pagination have been verified. Do not force uncertain classifications.

Korea NTB uses `backend/taxonomy/data/ntb_to_ics.csv` to map native technology
codes to ISO ICS. APCTT uses verified Drupal country and sector TIDs in
`backend/taxonomy/apctt_taxonomy.py`. Its public REST Export is
`https://www.apctt.org/api/technology-offers?_format=json`; live failures fall
back to `backend/sources/data/apctt_fallback.json`.

## Known limitations

- Crawler snapshots are not refreshed automatically.
- Some upstream services can be intermittent or block cloud-hosting egress.
- Live-source facet totals may be unavailable when the complete upstream
  catalogue is not locally indexed.
- The repository currently has no declared open-source license. Do not assume
  permission to redistribute the code or bundled source metadata without the
  appropriate APCTT and source-provider review.
- Production availability checks cover the API health, source registry and
  facet endpoint, but do not replace provider-specific monitoring.

The IP Australia adapter remains in the repository for reference but is not
registered as an active source. General patent-search records are intentionally
excluded because APTG is focused on technologies presented for transfer,
licensing or cooperation.
