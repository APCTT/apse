import httpx
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import unquote

from backend.sources.base import BaseSource
from backend.models.technology import Technology
from backend.config import settings

logger = logging.getLogger(__name__)


class KoreaNTBSource(BaseSource):
    id = "korea_ntb"
    name = "Korea National Technology Bank"
    country = "Republic of Korea"
    institution = "Korea Institute for Advancement of Technology (KIAT)"
    status = "Metadata search"
    url = "https://www.ntb.kr"
    ttl_seconds = 86400

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

        return Technology(
            id=f"ntb_{tech_id}",
            title=f("techName") or "Untitled",
            summary=f("summary"),
            sector=sector,
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
        )

    async def search(self, query: str, filters: dict) -> tuple[list[Technology], int]:
        page = int(filters.get("page", 1))
        params: dict = {
            "serviceKey": unquote(settings.KOREA_NTB_API_KEY),
            "numOfRows": "20",
            "pageNo": str(page),
        }
        if query:
            params["techName"] = query
        if filters.get("sector"):
            # NTB's external API only accepts a single category — use the first selected
            params["tcateNamep"] = filters["sector"].split(",")[0].strip()

        logger.info("NTB: search q=%r page=%d", query, page)
        try:
            # 23s gives the Korean govt API enough time from US servers (~12-18s latency)
            async with httpx.AsyncClient(timeout=23.0) as client:
                r = await client.get(settings.KOREA_NTB_BASE_URL, params=params)
            logger.info("NTB: HTTP %s totalBytes=%d", r.status_code, len(r.content))
            r.raise_for_status()
        except Exception as e:
            logger.error("NTB: request failed — %s: %s", type(e).__name__, e)
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
        logger.info("NTB: %d items (total=%d)", len(items), total_count)
        return items, total_count

    def is_healthy(self) -> bool:
        return True
