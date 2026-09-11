"""APCTT catalogue source with snapshot and opt-in live modes.

Production defaults to the reviewed snapshot because the APCTT website blocks
Render's shared outbound network. ``APCTT_SOURCE_MODE=live`` restores the
original request-time integration when upstream access becomes available.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from backend.sources.static_json_source import StaticJSONSource
from scripts.crawl_apctt import API_URL, HEADERS, normalize_record


logger = logging.getLogger(__name__)


class APCTTSource(StaticJSONSource):
    id = "apctt"
    name = "APCTT Technology Offers"
    country = "Asia and the Pacific"
    institution = "Asian and Pacific Centre for Transfer of Technology (APCTT)"
    url = "https://www.apctt.org/technology-offers"
    ttl_seconds = 86400
    transfer_type = "Technology transfer / cooperation"
    multi_country = True
    access_method = "Reviewed APCTT catalogue snapshot"
    last_indexed = "2026-09-11"
    org_default = "Asian and Pacific Centre for Transfer of Technology (APCTT)"


class APCTTLiveSource(APCTTSource):
    """Original live Drupal mode, retained for a future upstream reopening."""

    ttl_seconds = 3600
    requires_facet_preparation = True
    access_method = "Live APCTT catalogue with snapshot fallback"
    _MAX_PAGES = 100
    _RETRY_SECONDS = 300

    def __init__(self, api_url: str = API_URL):
        super().__init__()
        self._api_url = api_url
        self._cache_expires_at = 0.0
        self._refresh_lock: asyncio.Lock | None = None

    async def _request_page(self, page: int) -> list[dict]:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                self._api_url,
                params={"_format": "json", "page": page},
                headers=HEADERS,
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("APCTT export returned a non-list response")
        return [item for item in payload if isinstance(item, dict)]

    async def _refresh(self) -> None:
        if self._records and time.monotonic() < self._cache_expires_at:
            return
        if self._refresh_lock is None:
            self._refresh_lock = asyncio.Lock()
        async with self._refresh_lock:
            if self._records and time.monotonic() < self._cache_expires_at:
                return

            records: list[dict] = []
            seen_ids: set[str] = set()
            had_cached_records = bool(self._records)
            try:
                for page in range(self._MAX_PAGES):
                    raw_page = await self._request_page(page)
                    if not raw_page:
                        break
                    added = 0
                    for raw in raw_page:
                        record = normalize_record(raw)
                        if not record or record["id"] in seen_ids:
                            continue
                        seen_ids.add(record["id"])
                        records.append(record)
                        added += 1
                    if added == 0:
                        break
                if not records:
                    raise ValueError("APCTT live catalogue returned no published records")
            except Exception as exc:
                if not self._records:
                    super()._load()
                if not self._records:
                    raise
                self._cache_expires_at = time.monotonic() + self._RETRY_SECONDS
                logger.warning(
                    "APCTT live refresh failed (%s); serving %s",
                    type(exc).__name__,
                    "cached live catalogue" if had_cached_records else "reviewed snapshot",
                )
                return

            self._prepare_records(records)
            self._loaded = True
            self._cache_expires_at = time.monotonic() + self.ttl_seconds
            logger.info("APCTT: loaded %d live technology offers", len(records))

    async def prepare_facets(self) -> None:
        await self._refresh()

    async def search(self, query: str, filters: dict):
        await self._refresh()
        return await super().search(query, filters)


def create_apctt_source(mode: str, api_url: str = API_URL) -> APCTTSource:
    """Create the configured source without changing callers or source IDs."""
    if mode.strip().lower() == "live":
        return APCTTLiveSource(api_url=api_url)
    return APCTTSource()
