# Crawled source index operations

The production API does not crawl source websites during a user request.
Five source indexes are committed as JSON under `backend/sources/data/` and
loaded by `StaticJSONSource`. This keeps the Render web service small and
avoids a paid background worker or database.

## Current configuration

There is currently no GitHub Actions workflow, Render Cron Job, launchd job, or
other scheduler in this repository. Every crawler is a manual, full refresh
that writes directly to its source JSON file.

| Source | Command | Output | Last repository update |
|---|---|---|---|
| CSIR India | `python scripts/crawl_csir.py` | `csir_india.json` | 2026-06-23 |
| DOST-TAPI | `python scripts/crawl_dost_tapi.py` | `dost_tapi.json` | 2026-06-25 |
| Tech2Biz | `python scripts/crawl_tech2biz.py` | `tech2biz.json` | 2026-06-26 |
| JST Japan | `python -m backend.sources.crawl_jst` | `jst_japan.json` | 2026-06-30 |
| NRDC India | `python -m backend.sources.crawl_nrdc` | `nrdc_india.json` | 2026-07-06 |

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
python scripts/validate_crawled_data.py
git diff --stat -- backend/sources/data
git diff -- backend/sources/data/dost_tapi.json
```

Do not commit an unexpectedly small or empty output. The scripts perform full
refreshes and currently have no minimum-record safeguard. Git remains the
rollback mechanism for a bad crawl.

Tech2Biz also calls the free MyMemory translation API for every record. A
quota or translation failure can leave Thai text untranslated, so its diff
requires additional review.

## Recommended schedule before automation

Start with a reviewed manual refresh rather than an unattended schedule:

- CSIR, DOST-TAPI, JST, and NRDC: monthly
- Tech2Biz: every two or three months because the translation step is slower
  and depends on a third-party free quota
- Live API sources (Korea NTB and IP Australia): do not crawl; keep the
  existing on-demand API call and 24-hour search cache

Once two consecutive manual refreshes are clean, these commands can move to a
monthly GitHub Actions workflow. Keep crawling outside Render so the hosting
cost remains limited to the single web service. The workflow should open a
reviewable pull request instead of committing directly to the production
branch.
