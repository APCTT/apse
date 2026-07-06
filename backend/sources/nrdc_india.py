import json
import logging
from datetime import datetime
from pathlib import Path

from backend.sources.base import BaseSource
from backend.models.technology import Technology

logger = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).parent / "data" / "nrdc_india.json"


class NRDCIndiaSource(BaseSource):
    id = "nrdc_india"
    name = "NRDC India Technology Portal"
    country = "India"
    institution = "National Research Development Corporation (NRDC)"
    status = "Metadata search"
    url = "https://nrdcindia.com/Pages/Technology Available for Commercialization"
    ttl_seconds = 86400
    transfer_type = "Technology transfer / licensing"

    def __init__(self):
        self._records: list[dict] = []
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        if not _DATA_PATH.exists():
            logger.warning("NRDC: data file NOT FOUND at %s", _DATA_PATH)
            self._records = []
        else:
            with open(_DATA_PATH, encoding="utf-8-sig") as f:
                self._records = json.load(f)
            logger.warning("NRDC: loaded %d records from %s", len(self._records), _DATA_PATH)
        self._loaded = True

    def _to_technology(self, rec: dict) -> Technology:
        return Technology(
            id=rec["id"],
            title=rec["title"],
            summary=rec.get("summary", ""),
            sector=rec.get("sector", "Technology"),
            language="en",
            keywords=rec.get("keywords", []),
            country="India",
            source_id=self.id,
            source_name=self.name,
            url=rec["url"],
            fetched_at=datetime.utcnow(),
            org_name=rec.get("institute", "NRDC"),
            transfer_type="Technology transfer / licensing",
            dev_status=rec.get("trl", ""),
            reg_date="",
            sub_sector="",
        )

    async def search(self, query: str, filters: dict) -> tuple[list[Technology], int]:
        self._load()
        page = int(filters.get("page", 1))
        page_size = 20

        q = query.lower()
        sector_filters = [s.strip().lower() for s in (filters.get("sector") or "").split(",") if s.strip()]

        matched = []
        for rec in self._records:
            rec_sector = rec.get("sector", "").lower()
            if sector_filters and not any(sf in rec_sector for sf in sector_filters):
                continue
            if q:
                searchable = " ".join([
                    rec.get("title", ""),
                    rec.get("summary", ""),
                    rec.get("institute", ""),
                    " ".join(rec.get("keywords", [])),
                ]).lower()
                if q not in searchable:
                    continue
            matched.append(rec)

        total = len(matched)
        page_slice = matched[(page - 1) * page_size: page * page_size]
        return [self._to_technology(r) for r in page_slice], total

    def is_healthy(self) -> bool:
        return _DATA_PATH.exists()
