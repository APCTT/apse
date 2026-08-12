# Crawled source index operations

The production API does not crawl source websites during a user request.
Six source indexes are committed as JSON under `backend/sources/data/` and
loaded by `StaticJSONSource`. This keeps the Render web service small and
avoids a paid background worker or database.

## Current configuration

Crawler refreshes remain manual and reviewed; there is no unattended crawler
scheduler in this repository. GitHub Actions validates committed snapshots and
the deployed API, but does not replace production data automatically. The
safeguarded crawlers shown below write staging snapshots by default.

| Source | Command | Output | Last repository update |
|---|---|---|---|
| CSIR India | `python scripts/crawl_csir.py` | `csir_india.staging.json` | 2026-08-10 |
| DOST-TAPI | `python scripts/crawl_dost_tapi.py` | `dost_tapi.staging.json` | 2026-08-10 |
| Tech2Biz | `python scripts/crawl_tech2biz.py` | `tech2biz.staging.json` | 2026-08-10 |
| JST Japan | `python -m backend.sources.crawl_jst` | `jst_japan.json` | 2026-06-30 |
| NRDC India | `python -m backend.sources.crawl_nrdc` | `nrdc_india.staging.json` | 2026-08-10 |
| ITI Sri Lanka | `python scripts/crawl_iti_sri_lanka.py --output backend/sources/data/iti_sri_lanka.json --replace-production` | `iti_sri_lanka.json` | 2026-08-10 |

`scripts/crawl_slintec.py` is orphaned: the Slintec source and its output data
are not registered in the application.

## Safe manual refresh

Install the crawler-only dependencies in the existing virtual environment:

```sh
. .venv/bin/activate
python -m pip install -r scripts/requirements-crawl.txt
```

Run one crawler at a time, then validate and review its changes:

```sh
python scripts/crawl_dost_tapi.py
python scripts/crawl_dost_tapi.py \
  --output backend/sources/data/dost_tapi.json \
  --replace-production
python scripts/validate_crawled_data.py
git diff --stat -- backend/sources/data
```

CSIR, DOST-TAPI, and NRDC now default to staging output, retry failed detail
requests three times, reject excessive failure rates and unexpected record
count drops, and write snapshots atomically. Replacing a production JSON still
requires both an explicit production `--output` path and
`--replace-production`. Review the printed added/removed/changed counts before
replacement. The two NRDC records whose current source links return HTTP 404
are excluded from its searchable snapshot.

The ITI crawler is the exception: it writes a staging file by default, verifies
that ITI still labels the upstream page as `Available Technologies`, and blocks
outputs below 80 records. It does not crawl ITI's separate Commercialized
Technologies page. Review `iti_sri_lanka.staging.json` before using the explicit
production replacement command shown in the table. The current upstream page
contains 103 PDF links; one legacy numeric-host link is unreachable and is
excluded, leaving 102 searchable records.

Tech2Biz writes `backend/sources/data/tech2biz.staging.json` by default and
preserves the original Thai title and description. MyMemory translation is
optional (`--translate-mymemory`); quota and error messages are rejected and
never stored as content. Direct replacement of the production JSON requires
both an explicit output path and `--replace-production`. Review the staging
file and its validation results before replacing the production index. Staging
JSON files are ignored by Git so they cannot be committed accidentally.

Translate and classify the validated Thai staging data with Gemini only after
setting `GEMINI_API_KEY` in the ignored `.env` file or shell environment:

```sh
python scripts/enrich_tech2biz.py --limit 5 \
  --output backend/sources/data/tech2biz.enriched.sample.staging.json
python scripts/enrich_tech2biz.py
```

The enrichment script uses structured JSON output, processes five records per
request, checkpoints every successful batch, and defaults to approximately 129
requests for the full 645-record catalogue. It writes another staging file and
does not replace the production index.

## Recommended schedule before automation

Start with a reviewed manual refresh rather than an unattended schedule:

- CSIR, DOST-TAPI, JST, NRDC, and ITI: monthly
- Tech2Biz: every two or three months because the translation step is slower
  and depends on a third-party free quota
- Live API source (Korea NTB): do not crawl; keep the existing on-demand API
  call and 24-hour search cache

Once two consecutive manual refreshes are clean, these commands can move to a
monthly GitHub Actions workflow. Keep crawling outside Render so the hosting
cost remains limited to the single web service. The workflow should open a
reviewable pull request instead of committing directly to the production
branch.
