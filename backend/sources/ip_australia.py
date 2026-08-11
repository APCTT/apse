import logging
from datetime import datetime, timezone

import httpx

from backend.sources.base import BaseSource
from backend.models.technology import Technology

logger = logging.getLogger(__name__)


class IPAustraliaSource(BaseSource):
    id = "ip_australia"
    name = "IP Australia Patent Search"
    country = "Australia"
    institution = "IP Australia"
    # Keep the shared source-type contract used by filtering and merged
    # pagination. User-facing copy clarifies that these are patent records.
    status = "Metadata search"
    url = "https://www.ipaustralia.gov.au/patents"
    ttl_seconds = 86400
    transfer_type = ""

    # This is the same unauthenticated endpoint used by IP Australia's public
    # Australian Patent Search website. It is preferable to the older external
    # token API, which adds credentials without providing richer card data.
    _SEARCH_URL = "https://production.api.ipaustralia.gov.au/public/ipright-search-api/v1/patents"

    async def search(self, query: str, filters: dict) -> tuple[list[Technology], int]:
        if not query:
            return [], 0

        page = int(filters.get("page", 1))
        page_size = 20
        params = {
            "query": query,
            # Include abstract text in matching where IP Australia has it. The
            # result payload still contains metadata rather than abstract text.
            "searchAbstractText": "true",
            "limit": page_size,
            "offset": max(0, page - 1) * page_size,
            "orderBy": "filingDate",
            "order": "desc",
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(self._SEARCH_URL, params=params)
            logger.info("IPAustralia: search status=%s", r.status_code)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("IPAustralia: search failed status=%s", e.response.status_code)
            raise
        except httpx.HTTPError as e:
            logger.error("IPAustralia: search failed (%s)", type(e).__name__)
            raise

        data = r.json()
        total = int(data.get("count") or 0)
        items = [self._normalize(hit) for hit in (data.get("results") or [])]
        logger.info("IPAustralia: %d results (total=%d)", len(items), total)
        return items, total

    def _normalize(self, hit: dict) -> Technology:
        title = hit.get("inventionTitle") or hit.get("applicationNumber") or "Untitled patent record"
        applicants = hit.get("applicants") or ""
        if isinstance(applicants, list):
            first = applicants[0] if applicants else ""
            org = first.get("name", "") if isinstance(first, dict) else str(first)
        else:
            org = str(applicants).split(";")[0].strip()
        filing_date = hit.get("filingDate") or ""
        if len(filing_date) == 8:
            filing_date = f"{filing_date[:4]}-{filing_date[4:6]}-{filing_date[6:]}"
        priority_date = hit.get("earliestPriorityDate") or ""
        if len(priority_date) == 8:
            priority_date = f"{priority_date[:4]}-{priority_date[4:6]}-{priority_date[6:]}"
        app_num = hit.get("auApplicationNumber") or hit.get("identifier") or hit.get("applicationNumber") or ""
        patent_type = str(hit.get("patentType") or "").strip()
        return Technology(
            id=f"ipau_{app_num}",
            source_id=self.id,
            source_name=self.name,
            title=title,
            # The list API does not return abstract text. An empty summary lets
            # the frontend use its dedicated patent metadata card instead of
            # presenting a synthetic sentence as a technology description.
            summary="",
            sector="Other / Unclassified",
            country="Australia",
            language="en",
            org_name=org,
            transfer_type="",
            dev_status=hit.get("applicationStatus") or "",
            reg_date=filing_date,
            keywords=[],
            sub_sector="",
            url=f"https://ipsearch.ipaustralia.gov.au/patents/{app_num}" if app_num else "",
            fetched_at=datetime.now(timezone.utc),
            record_type="Patent record",
            reference_id=app_num,
            patent_type=patent_type,
            priority_date=priority_date,
            source_sector="",
            sector_codes=[],
            sector_labels=[],
            taxonomy_scheme="",
            taxonomy_version="",
            classification_method="unclassified",
            classification_confidence="",
        )

    def is_healthy(self) -> bool:
        return True
