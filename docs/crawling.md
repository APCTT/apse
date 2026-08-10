# Crawled source index operations

The production API does not crawl source websites during a user request.
Six source indexes are committed as JSON under `backend/sources/data/` and
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
python scripts/validate_crawled_data.py
git diff --stat -- backend/sources/data
git diff -- backend/sources/data/dost_tapi.json
```

Do not commit an unexpectedly small or empty output. The scripts perform full
refreshes and currently have no minimum-record safeguard. Git remains the
rollback mechanism for a bad crawl.

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
- Live API sources (Korea NTB and IP Australia): do not crawl; keep the
  existing on-demand API call and 24-hour search cache

Once two consecutive manual refreshes are clean, these commands can move to a
monthly GitHub Actions workflow. Keep crawling outside Render so the hosting
cost remains limited to the single web service. The workflow should open a
reviewable pull request instead of committing directly to the production
branch.
