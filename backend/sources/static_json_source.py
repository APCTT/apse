import json
import logging
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from backend.sources.base import BaseSource
from backend.models.technology import Technology
from backend.taxonomy.iso_ics import (
    TAXONOMY_SCHEME,
    TAXONOMY_VERSION,
    classify_sector,
    matches_sector_filter,
)

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"


class StaticJSONSource(BaseSource):
    """Base for sources backed by a pre-crawled JSON file of records.

    Subclasses set the BaseSource class attrs plus `language`, `org_default`
    (fallback org_name when a record has no "institute") and `encoding` where
    they differ from the defaults below.
    """

    status = "Metadata search"
    language: str = "en"
    org_default: str = ""
    encoding: str = "utf-8-sig"
    sector_filter_supported = True
    facet_count_supported = True
    sector_provenance: str = "source"

    def __init__(self):
        self._data_path = _DATA_DIR / f"{self.id}.json"
        self._records: list[dict] = []
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        if not self._data_path.exists():
            logger.warning("%s: data file NOT FOUND at %s", self.id, self._data_path)
            self._records = []
        else:
            with open(self._data_path, encoding=self.encoding) as f:
                self._records = json.load(f)
            for rec in self._records:
                source_sector = rec.get("sector", "")
                classification = classify_sector(
                    source_sector,
                    title=rec.get("title", ""),
                    summary=rec.get("summary", ""),
                    keywords=rec.get("keywords", []),
                )
                if self.sector_provenance == "legacy_keyword":
                    content_classification = classify_sector(
                        "",
                        title=rec.get("title", ""),
                        summary=rec.get("summary", ""),
                        keywords=rec.get("keywords", []),
                    )
                    if content_classification.codes:
                        classification = replace(
                            content_classification,
                            source_sector=source_sector,
                            method="legacy_content_classification",
                            confidence="low",
                        )
                    elif classification.codes:
                        classification = replace(
                            classification,
                            method="legacy_keyword_mapping",
                            confidence="low",
                        )
                rec["_sector_classification"] = classification
            logger.info("%s: loaded %d records from %s", self.id, len(self._records), self._data_path)
        self._loaded = True

    def _to_technology(self, rec: dict) -> Technology:
        classification = rec["_sector_classification"]
        return Technology(
            id=rec["id"],
            title=rec["title"],
            summary=rec.get("summary", ""),
            sector=classification.primary_label,
            language=self.language,
            keywords=rec.get("keywords", []),
            country=self.country,
            source_id=self.id,
            source_name=self.name,
            url=rec["url"],
            fetched_at=datetime.utcnow(),
            org_name=rec.get("institute", self.org_default),
            transfer_type=self.transfer_type,
            dev_status=rec.get("trl", ""),
            reg_date="",
            sub_sector="",
            source_sector=classification.source_sector,
            sector_codes=list(classification.codes),
            sector_labels=list(classification.labels),
            taxonomy_scheme=TAXONOMY_SCHEME,
            taxonomy_version=TAXONOMY_VERSION,
            classification_method=classification.method,
            classification_confidence=classification.confidence,
        )

    async def search(self, query: str, filters: dict) -> tuple[list[Technology], int]:
        self._load()
        page = int(filters.get("page", 1))
        page_size = 20

        q = query.lower()
        sector_filters = [s.strip() for s in (filters.get("sector") or "").split(",") if s.strip()]

        matched = []
        for rec in self._records:
            classification = rec["_sector_classification"]
            if not matches_sector_filter(classification, sector_filters):
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

    def sector_facets(self) -> dict[str, int]:
        self._load()
        counts: dict[str, int] = {}
        for rec in self._records:
            classification = rec["_sector_classification"]
            for code in classification.codes:
                counts[code] = counts.get(code, 0) + 1
        return counts

    def facet_records(self):
        self._load()
        for rec in self._records:
            yield {
                "searchable": " ".join([
                    rec.get("title", ""),
                    rec.get("summary", ""),
                    rec.get("institute", ""),
                    " ".join(rec.get("keywords", [])),
                ]).lower(),
                "classification": rec["_sector_classification"],
            }

    def is_healthy(self) -> bool:
        return self._data_path.exists()
