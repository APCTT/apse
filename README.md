# APSE Technology Gateway

A federated search tool for technology transfer databases across Asia and the Pacific. Built for APCTT (Asian and Pacific Centre for Transfer of Technology), a UN ESCAP body. Instead of visiting each country's technology database separately, you search once here and get results from all of them together.

Plain HTML/CSS/JS frontend, no build step. FastAPI backend. Deployed on Render's free tier.

## What's in here

The homepage has two views you switch between with the nav: **Search** (the search bar, filters, and results grid) and **Technology sources** (a card for each database with its own description and a link to search just that one). An "About" section sits underneath both as a shared footer.

Search results from multiple databases are merged into one page using round robin, so you get a mix from every source instead of one source's results dumped first. A stats card at the top shows total technologies, total sources, and total countries, with a row of clickable chips (one per source) that filter the results down to just that source when you click one.

## Sources currently wired in

| Source | Country | How it works |
|---|---|---|
| Korea National Technology Bank | South Korea | Live API, fetched fresh each search |
| WIPO PATENTSCOPE | International | Redirect only — opens WIPO's own search with your query filled in |
| IP Australia Patent Search | Australia | Live API, but only works if you type an actual keyword |
| CSIR India Technology Portal | India | Crawled once, served from a local JSON file |
| DOST-TAPI | Philippines | Crawled once, served from a local JSON file |
| Tech2Biz | Thailand | Crawled once, served from a local JSON file |
| JST Japan Patent Portfolio | Japan | Crawled once, served from a local JSON file |
| NRDC India | India | Crawled once, served from a local JSON file |

The five crawled-and-cached sources (CSIR, DOST-TAPI, Tech2Biz, JST, NRDC) all share one class, `StaticJSONSource` in `backend/sources/static_json_source.py`. If you're adding a new source that's basically "crawl a site once, save it as JSON, search that JSON," subclass this instead of writing the load/search logic again — that's what it's there for.

## How the pieces fit together

```
frontend/
  index.html      the whole page markup, both views + about section
  app.js          all the JS — search, filters, chips, the source cards page
  styles.css      all the styling

backend/
  main.py                 FastAPI app, CORS, rate limiting, security headers
  config.py                reads environment variables (API keys etc.)
  routers/
    search.py              GET /api/v1/search — fans a query out to every source
    sources.py              GET /api/v1/sources — lists the registered sources
  sources/
    base.py                 the interface every source class implements
    static_json_source.py   shared base for the five crawled sources
    registry.py              the list of which sources are actually active
    korea_ntb.py, wipo_patentscope.py, ip_australia.py   the three "live" sources
    csir_india.py, dost_tapi.py, tech2biz.py, jst_japan.py, nrdc_india.py   the five crawled ones
    data/*.json              the actual crawled records for those five
  cache/
    ttl_cache.py             caches search results so repeat queries don't re-hit every source

scripts/
  crawl_*.py                the one-off scripts that produced the data/*.json files
```

`scripts/crawl_slintec.py` is left over from a source (Slintec, Sri Lanka) that got crawled once and then removed from the site — its data file and source class are already deleted, so this script currently has nothing to point at. Either wire Slintec back in properly or delete the script; right now it just sits there unused.

Crawler refreshes are manual and are not scheduled by Render or GitHub. See
[`docs/crawling.md`](docs/crawling.md) for the current source inventory,
crawler-only dependencies, validation command, and safe refresh procedure.

## Running it locally

You need Python 3.11 or newer.

```
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.

The app runs without API credentials using its bundled static data sources. To
also enable the live Korea NTB source, make a `.env` file in the project root
(don't commit it — it's already gitignored):

```
KOREA_NTB_API_KEY=your_key
KOREA_NTB_BASE_URL=https://apis.data.go.kr/B552536/tech_4/techall
CACHE_TTL_SECONDS=86400
```

`IP_AUSTRALIA_CLIENT_ID` / `IP_AUSTRALIA_CLIENT_SECRET` are optional — without them, IP Australia just won't show up as a source.

Start both the backend and frontend:

```
./scripts/dev.sh
```

Then open `http://127.0.0.1:5501`. The frontend automatically uses the local
API at `http://127.0.0.1:8000` when served from localhost, and the deployed API
everywhere else. The APCTT-aligned theme is the default; append
`?theme=classic` to compare it with the original APSE design.

## Deploying

There are two Render services: `apse-api` (the backend) and `apse-frontend` (the static site). Both are set to **manual deploy** — pushing to GitHub does not automatically redeploy either one. After pushing, go into each service's Render dashboard and hit deploy.

Render's free tier has no persistent disk and the service spins down after about 15 minutes of no traffic. The first request after that takes 20-40 seconds to wake back up — the frontend already handles this (it retries for a while and shows a "waking up" message instead of just failing).

One catch worth knowing: Render's actual build command is `pip install -r requirements.txt`, reading from the **root** `requirements.txt`, not `backend/requirements.txt` — even though `render.yaml` in this repo says otherwise. If you ever "clean up" the duplicate root `requirements.txt` because it looks redundant, the deploy will break. Keep both in sync, or check the Render dashboard's actual build command before touching either file.

## Adding a new source

If it's a live API: create `backend/sources/<name>.py`, subclass `BaseSource`, implement `search()` and `is_healthy()`, add it to `backend/sources/registry.py`.

If it's a site you're going to crawl once and store locally: write a one-off crawl script in `scripts/`, save the output to `backend/sources/data/<name>.json`, then create a source class subclassing `StaticJSONSource` (see `csir_india.py` for the shortest example — it's about 8 lines).

Either way, once it's in `registry.py`, the search API, caching, and frontend filters all pick it up automatically. If the source has sectors that aren't already in the `SECTOR_OPTIONS` list near the top of `app.js`, add them there too, or they won't show up as filter options.

## Issues we ran into while building this (so you don't have to rediscover them)

**Running the frontend locally on the "wrong" port gives you CORS errors.** `backend/main.py` only allows a fixed list of origins to call the API: `https://apsei.onrender.com`, `https://apctt.org`, `https://www.apctt.org`, `http://localhost:5501`, and `http://127.0.0.1:5501`. If you serve the frontend locally on a different port — VS Code's Live Server defaults to 5500, `python -m http.server` picks whatever port you give it — calls to the deployed backend will fail with a CORS error in the console, and it'll look like the backend is broken when it's actually just not expecting requests from that origin. Either serve the frontend on port 5501 to match what's already allowed, or add your local port to the `allow_origins` list in `main.py` (don't forget to remove it again before deploying, or just leave it since it's only a localhost entry).

**The search results cache doesn't last as long as it looks like it should.** `backend/cache/ttl_cache.py` uses a SQLite file with a 24-hour TTL, which sounds like it should hold results for a full day. In practice, Render's free tier wipes the filesystem every time the service spins down from inactivity, so the cache resets far more often than the TTL suggests. It's not broken, it just isn't doing what the number implies. If this ever actually matters (higher traffic, need for real day-long caching), that means either a paid Render disk or moving to something like Redis — not a code fix on our end.

**Editing the frontend and not seeing your changes.** `app.js` and `styles.css` are loaded with plain `<script src="app.js">` / `<link href="styles.css">` tags, no cache-busting. Browsers will happily keep serving an old cached copy of these files even after you've edited them and reloaded the page — a full refresh sometimes isn't enough. Both files are now loaded with a `?v=` version number on the end (`app.js?v=4`); bump that number whenever you ship a real change to either file, or people's browsers (including your own, while testing) may quietly run stale code and make you think a fix didn't work when it did.

**The search results cache key was missing a filter.** The cache key for `/api/v1/search` is built from the query and filters — but for a while it didn't include the `exclude` parameter, meaning two searches that only differed by `exclude` could collide and one would silently get back the other's cached results. It never actually broke anything live since nothing in the frontend was using `exclude` at the time, but it's the kind of bug that only shows up once something starts using that parameter and gets confusing results with no obvious cause. Worth remembering if you ever wire `exclude` into a real feature — check the cache key includes every parameter that changes the result.

**Chips that filter by source need to fully replace the selection, not add to it.** Early on, clicking a source chip added it to whatever was already selected instead of replacing it — so clicking "WIPO" right after clicking "DOST" left both active, and the results looked like the wrong source's data was showing up. It wasn't wrong data, it was two sources still selected at once with no visual cue. If you build another filter chip row, make each click a clean replace (or make the additive behavior obvious in the UI) rather than assuming users will notice a previous selection is still active.

## A few things worth doing at some point (not done yet, just flagging)

These aren't broken, they're just gaps that would matter more if this gets more traffic or more public visibility:

- A Content-Security-Policy header, so that if a crawled source ever returned something malicious, the browser has a second layer of protection beyond escaping the text (which is already done in `technologyCard()` in `app.js`).
- Dependency scanning (Dependabot or similar) — nothing is currently watching for known vulnerabilities in `fastapi`, `httpx`, etc. Worth turning on later, but be aware GitHub's default Dependabot config opens a PR for every newer version, not just security fixes, so it can get noisy if you don't scope it to security-only updates.
- An HSTS header, mostly relevant if this ever gets its own custom domain instead of `*.onrender.com`.
- Some way to notice if the API is getting hammered by one IP repeatedly — right now it just quietly rate-limits and moves on, with nothing logged anywhere you'd see it.
- Rotating the API keys (Korea NTB, IP Australia) every so often, just as general hygiene for keys that don't expire on their own.

None of these are urgent. The system works fine without them — they're the kind of thing worth doing if someone ever formally security-reviews this, not things that are currently causing problems.
