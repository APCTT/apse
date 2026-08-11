# Troubleshooting

## Local frontend cannot call the API

The backend CORS allow-list includes `http://localhost:5501` and
`http://127.0.0.1:5501`. Serving the frontend from another origin or port can
produce a browser CORS error even when the API itself is healthy. Prefer
`./scripts/dev.sh` or update `backend/main.py` deliberately for another local
origin.

## Frontend changes appear stale

The frontend has no build-time asset hashing. Browsers and CDNs can retain
older copies of `app.js` or `styles.css`. Update the `?v=` query versions in
`frontend/index.html` when deploying meaningful frontend changes, then verify
the deployed HTML references the new values.

## Cache data resets

Search analytics, semantic data, and result caches use local SQLite files by
default. A long TTL does not make those files durable. Without a persistent
disk or external database they can reset during a replacement deployment,
service recreation, or another ephemeral-filesystem reset.

## A filter appears to return the wrong cached result

Every request parameter that changes search results must also participate in
the cache key. This previously affected the `exclude` parameter. When adding a
new filter, update and test both request handling and cache-key construction.

## Source chips appear additive

The source chip row is intentionally single-select: selecting a chip replaces
the previous chip selection. The full source filter supports multiple values.
Keep these interaction models distinct when modifying filter behavior.

## APCTT live catalogue is unavailable

The APCTT Drupal export can return HTTP 403 to some cloud-hosting egress ranges.
The integration serves the last reviewed bundled fallback snapshot and retries
the live catalogue later. Check backend logs and the age of
`backend/sources/data/apctt_fallback.json` before treating an empty or stale
response as an application parsing failure.
