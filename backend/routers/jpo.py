import logging
import threading
import time

from fastapi import APIRouter, HTTPException, Path

from backend.integrations.jpo_client import jpo_client

logger = logging.getLogger(__name__)
router = APIRouter()

# JPO's account-level quota is shared across all users of this app (400-800
# calls/day total) and their data only updates once daily, so repeated
# lookups of the same application number are cached generously here to
# avoid burning through that scarce quota. Kept separate from the main
# TTLCache, which is specialized for the search endpoint's response shape.
_JPO_CACHE_TTL_SECONDS = 12 * 60 * 60
_jpo_cache: dict[str, tuple[dict, float]] = {}
_jpo_cache_lock = threading.Lock()


def _cache_get(key: str) -> dict | None:
    with _jpo_cache_lock:
        entry = _jpo_cache.get(key)
        if entry is None:
            return None
        data, expires_at = entry
        if time.time() > expires_at:
            del _jpo_cache[key]
            return None
        return data


def _cache_set(key: str, data: dict) -> None:
    with _jpo_cache_lock:
        _jpo_cache[key] = (data, time.time() + _JPO_CACHE_TTL_SECONDS)


@router.get("/jpo/patent-status/{application_number}")
async def jpo_patent_status(
    application_number: str = Path(
        ...,
        pattern=r"^\d{10}$",
        description="10-digit Japanese patent application number, e.g. 2020008423",
    ),
):
    cached = _cache_get(application_number)
    if cached is not None:
        return cached

    try:
        data = await jpo_client.get_patent_status(application_number)
    except Exception as e:
        logger.error("JPO lookup failed for %s — %s: %s", application_number, type(e).__name__, e)
        raise HTTPException(
            status_code=502,
            detail="Could not reach the JPO Patent Information Retrieval API. Please try again shortly.",
        )

    _cache_set(application_number, data)
    return data
