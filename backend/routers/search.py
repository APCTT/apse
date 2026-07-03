import asyncio
import hashlib
import json
import logging
from typing import Optional

from fastapi import APIRouter, Query
from backend.sources.registry import SOURCES, SOURCE_MAP
from backend.models.response import SearchResponse
from backend.cache.ttl_cache import cache
from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _cache_key(params: dict) -> str:
    serialized = json.dumps(params, sort_keys=True)
    return hashlib.md5(serialized.encode()).hexdigest()


@router.get("/search", response_model=SearchResponse)
async def search(
    q: Optional[str] = Query(None, max_length=200),
    country: Optional[str] = Query(None, max_length=300),
    sector: Optional[str] = Query(None, max_length=300),
    source: Optional[str] = Query(None, max_length=300),
    exclude: Optional[str] = Query(None, max_length=300),
    language: Optional[str] = Query(None, max_length=50),
    transfer_type: Optional[str] = Query(None, max_length=300),
    page: int = Query(1, ge=1, le=100_000),
):
    query = q or ""
    filters = {k: v for k, v in {"country": country, "sector": sector, "page": page}.items() if v}

    key = _cache_key({"q": query, "country": country, "sector": sector,
                       "source": source, "language": language,
                       "transfer_type": transfer_type, "page": page})
    cached = cache.get(key)
    if cached is not None:
        results, source_totals = cached
        return SearchResponse(
            query=query,
            total=len(results),
            sources_hit=len({r.source_id for r in results}),
            results=results,
            cached=True,
            source_totals=source_totals,
        )

    active_sources = SOURCES
    if source:
        source_ids = {x.strip() for x in source.split(",") if x.strip()}
        active_sources = [s for s in SOURCES if s.id in source_ids]
    if exclude:
        excluded_ids = {x.strip() for x in exclude.split(",")}
        active_sources = [s for s in active_sources if s.id not in excluded_ids]
    if country:
        countries = {c.strip() for c in country.split(",") if c.strip()}
        active_sources = [s for s in active_sources if s.country in countries or s.country == "Global"]
    if transfer_type:
        transfer_types = {t.strip() for t in transfer_type.split(",") if t.strip()}
        active_sources = [s for s in active_sources if s.transfer_type in transfer_types]

    # NTB API (Korean govt) takes 12-18s from Render's US servers — needs extra budget
    SOURCE_TIMEOUTS = {"korea_ntb": 25.0}

    async def safe_search(src):
        timeout = SOURCE_TIMEOUTS.get(src.id, 10.0)
        try:
            return src.id, await asyncio.wait_for(src.search(query, filters), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Source %s timed out after %.0fs for query=%r", src.id, timeout, query)
            return src.id, ([], 0)
        except Exception as e:
            logger.error("Source %s failed — %s: %s", src.id, type(e).__name__, e)
            return src.id, ([], 0)

    raw = await asyncio.gather(*[safe_search(s) for s in active_sources])

    results = []
    source_totals = {}
    for src_id, (items, total_count) in raw:
        results.extend(items)
        if total_count > 0:
            source_totals[src_id] = total_count

    if language:
        results = [r for r in results if r.language.lower() == language.lower()]

    cache.set(key, (results, source_totals), ttl=settings.CACHE_TTL_SECONDS)

    return SearchResponse(
        query=query,
        total=len(results),
        sources_hit=len({r.source_id for r in results}),
        results=results,
        cached=False,
        source_totals=source_totals,
    )
