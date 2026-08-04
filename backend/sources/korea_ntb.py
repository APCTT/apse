import httpx
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import unquote

from backend.sources.base import BaseSource
from backend.models.technology import Technology
from backend.config import settings
from backend.taxonomy.iso_ics import TAXONOMY_SCHEME, TAXONOMY_VERSION, classify_sector

logger = logging.getLogger(__name__)


class KoreaNTBSource(BaseSource):
    id = "korea_ntb"
    name = "Korea National Technology Bank"
    country = "Republic of Korea"
    institution = "Korea Institute for Advancement of Technology (KIAT)"
    status = "Metadata search"
    url = "https://www.ntb.kr"
    ttl_seconds = 86400
    # NTB provides official technology categories. We normalize those
    # categories to ISO ICS and filter a larger live result window locally.
    # Facet counts remain unavailable because the full catalogue is not stored.
    sector_filter_supported = True

    def _normalize(self, item: ET.Element) -> Technology:
        def f(tag: str) -> str:
            return (item.findtext(tag) or "").strip()

        tech_id = f("stechNum")
        sector = f("tcateNamep") or f("tcateNamem") or "Uncategorized"
        kw_raw = f("keyword")
        app_fld = f("appFld")
        keywords = [k.strip() for k in kw_raw.split(";") if k.strip()]
        if app_fld:
            keywords += [k.strip() for k in app_fld.split(",") if k.strip()]
        title = f("techName") or "Untitled"
        summary = f("summary")
        classification = classify_sector(
            sector,
            title=title,
            summary=summary,
            keywords=keywords,
        )

        return Technology(
            id=f"ntb_{tech_id}",
            title=title,
            summary=summary,
            sector=classification.primary_label,
            language="Korean",
            keywords=keywords,
            country="Republic of Korea",
            source_id=self.id,
            source_name=self.name,
            url=f"https://www.ntb.kr/market/selectFullTechAndRecommend.do?techKey=&stechNum={tech_id}" if tech_id else self.url,
            fetched_at=datetime.utcnow(),
            org_name=f("orgName"),
            transfer_type=f("transType"),
            dev_status=f("devStatusName"),
            reg_date=f("regDate"),
            sub_sector=f("tcateNamem"),
            source_sector=sector,
            sector_codes=list(classification.codes),
            sector_labels=list(classification.labels),
            taxonomy_scheme=TAXONOMY_SCHEME,
            taxonomy_version=TAXONOMY_VERSION,
            classification_method=classification.method,
            classification_confidence=classification.confidence,
        )

    async def search(self, query: str, filters: dict) -> tuple[list[Technology], int]:
        page = int(filters.get("page", 1))
        selected_sectors = [
            value.strip()
            for value in (filters.get("sector") or "").split(",")
            if value.strip()
        ]
        # A sector-filtered request needs a wider upstream window because NTB
        # does not accept ISO ICS codes. Fetch one 100-record window, normalize
        # its native categories, then expose ordinary 20-record pages.
        upstream_page = 1 if selected_sectors else page
        rows = 100 if selected_sectors else 20
        params: dict = {
            "serviceKey": unquote(settings.KOREA_NTB_API_KEY),
            "numOfRows": str(rows),
            "pageNo": str(upstream_page),
        }
        if query:
            params["techName"] = query
        logger.info("NTB: search page=%d query_present=%s", page, bool(query))
        try:
            # 23s gives the Korean govt API enough time from US servers (~12-18s latency)
            async with httpx.AsyncClient(timeout=23.0) as client:
                r = await client.get(settings.KOREA_NTB_BASE_URL, params=params)
            logger.info("NTB: HTTP %s totalBytes=%d", r.status_code, len(r.content))
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("NTB: HTTP request failed status=%s", e.response.status_code)
            raise
        except httpx.HTTPError as e:
            logger.error("NTB: request failed (%s)", type(e).__name__)
            raise

        try:
            root = ET.fromstring(r.text)
        except ET.ParseError as e:
            logger.error("NTB: XML parse error — %s", e)
            raise

        result_code = root.findtext(".//resultCode") or ""
        if result_code != "00":
            result_message = root.findtext(".//resultMsg") or "Unknown API error"
            logger.warning("NTB: resultCode=%s msg=%s", result_code, result_message)
            raise RuntimeError(f"NTB API returned resultCode={result_code}: {result_message}")

        total_count = int(root.findtext(".//totalCount") or "0")
        items = [self._normalize(item) for item in root.findall(".//item")]
        if selected_sectors:
            items = [
                item
                for item in items
                if self._matches_sector_codes(item.sector_codes, selected_sectors)
            ]
            total_count = len(items)
            start = (page - 1) * 20
            items = items[start:start + 20]
        logger.info("NTB: %d items (total=%d)", len(items), total_count)
        return items, total_count

    @staticmethod
    def _matches_sector_codes(record_codes: list[str], selected_codes: list[str]) -> bool:
        return any(
            record_code == selected or record_code.startswith(f"{selected}.")
            for selected in selected_codes
            for record_code in record_codes
        )

    def is_healthy(self) -> bool:
        return True
