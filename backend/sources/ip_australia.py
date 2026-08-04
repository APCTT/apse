import asyncio
import logging
import time
from datetime import datetime
import httpx
from backend.sources.base import BaseSource
from backend.models.technology import Technology
from backend.config import settings
from backend.taxonomy.iso_ics import TAXONOMY_SCHEME, TAXONOMY_VERSION, classify_sector

logger = logging.getLogger(__name__)


class IPAustraliaSource(BaseSource):
    id = "ip_australia"
    name = "IP Australia Patent Search"
    country = "Australia"
    institution = "IP Australia"
    status = "Metadata search"
    url = "https://www.ipaustralia.gov.au/patents"
    ttl_seconds = 86400
    transfer_type = "Patent licensing"

    _TOKEN_URL = "https://production.api.ipaustralia.gov.au/public/external-token-api/v1/access_token"
    _SEARCH_URL = "https://production.api.ipaustralia.gov.au/public/australian-patent-search-api/v1/search/quick"

    def __init__(self):
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._lock: asyncio.Lock | None = None

    async def _get_token(self) -> str:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if self._token and time.time() < self._token_expiry - 30:
                return self._token

            cid = settings.IP_AUSTRALIA_CLIENT_ID
            csec = settings.IP_AUSTRALIA_CLIENT_SECRET
            logger.info("IPAustralia: fetching token (client_id=%s...)", cid[:8] if cid else "MISSING")

            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    self._TOKEN_URL,
                    data={"grant_type": "client_credentials"},
                    auth=(cid, csec),
                )

            logger.info("IPAustralia: token response status=%s", r.status_code)
            r.raise_for_status()
            body = r.json()
            self._token = body["access_token"]
            self._token_expiry = time.time() + int(body.get("expires_in", 3600))
            logger.info("IPAustralia: token OK, expires in %ss", body.get("expires_in"))
            return self._token

    async def search(self, query: str, filters: dict) -> tuple[list[Technology], int]:
        if not query:
            return [], 0

        try:
            token = await self._get_token()
        except httpx.HTTPStatusError as e:
            logger.error("IPAustralia: token fetch failed status=%s", e.response.status_code)
            raise
        except httpx.HTTPError as e:
            logger.error("IPAustralia: token fetch failed (%s)", type(e).__name__)
            raise

        page = int(filters.get("page", 1))
        payload = {
            "query": query,
            "searchType": "DETAILS",
            "searchMode": "QUICK_NO_ABSTRACT",
            "pageSize": 20,
            "pageNumber": page - 1,
            "sort": {"field": "FILING_DATE", "direction": "DESC"},
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    self._SEARCH_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                )
            logger.info("IPAustralia: search status=%s", r.status_code)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("IPAustralia: search failed status=%s", e.response.status_code)
            raise
        except httpx.HTTPError as e:
            logger.error("IPAustralia: search failed (%s)", type(e).__name__)
            raise

        data = r.json()
        total = int(data.get("totalHits") or 0)
        items = [self._normalize(hit) for hit in (data.get("results") or [])]
        logger.info("IPAustralia: %d results (total=%d)", len(items), total)
        return items, total

    def _normalize(self, hit: dict) -> Technology:
        titles = hit.get("title") or []
        title = titles[0] if titles else (hit.get("applicationNumber") or "Untitled")
        applicants = hit.get("applicants") or []
        org = applicants[0] if applicants else ""
        filing_date = hit.get("filingDate") or ""
        if len(filing_date) == 8:
            filing_date = f"{filing_date[:4]}-{filing_date[4:6]}-{filing_date[6:]}"
        app_num = hit.get("applicationNumber") or ""
        summary = f"Australian patent application {app_num}. Filed: {filing_date}. Status: {hit.get('applicationStatus') or 'Unknown'}."
        classification = classify_sector("Patents", title=title, summary=summary)
        return Technology(
            id=f"ipau_{app_num}",
            source_id=self.id,
            source_name=self.name,
            title=title,
            summary=summary,
            sector=classification.primary_label,
            country="Australia",
            language="en",
            org_name=org,
            transfer_type="Patent licensing",
            dev_status=hit.get("applicationStatus") or "",
            reg_date=filing_date,
            keywords=[],
            sub_sector="",
            url=f"https://ipsearch.ipaustralia.gov.au/patents/{app_num}" if app_num else "",
            fetched_at=datetime.utcnow(),
            source_sector="Patents",
            sector_codes=list(classification.codes),
            sector_labels=list(classification.labels),
            taxonomy_scheme=TAXONOMY_SCHEME,
            taxonomy_version=TAXONOMY_VERSION,
            classification_method=classification.method,
            classification_confidence=classification.confidence,
        )

    def is_healthy(self) -> bool:
        return bool(settings.IP_AUSTRALIA_CLIENT_ID)
