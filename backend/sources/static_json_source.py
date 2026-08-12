import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from backend.sources.base import BaseSource
from backend.models.technology import Technology
from backend.search.semantic import (
    SemanticQueryContext,
    searchable_text,
    semantic_search,
)
from backend.taxonomy.iso_ics import (
    ICS_LABELS,
    ICS_TOP_LEVEL_LABELS,
    OTHER_SECTOR_CODE,
    OTHER_SECTOR_LABEL,
    SectorClassification,
    TAXONOMY_SCHEME,
    TAXONOMY_VERSION,
    classify_sector,
    matches_sector_filter,
    top_level_sector_codes,
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
    access_method = "Reviewed snapshot"

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
                explicit_codes = tuple(
                    dict.fromkeys(
                        str(code).strip()
                        for code in (rec.get("sector_codes") or [])
                        if str(code).strip() in ICS_LABELS
                    )
                )
                explicit_code = str(rec.get("sector_code", "")).strip()
                if explicit_codes:
                    confidence = str(
                        rec.get("classification_confidence", "high")
                    ).strip()
                    if confidence not in {"high", "medium", "low"}:
                        confidence = "low"
                    classification = SectorClassification(
                        source_sector=source_sector,
                        codes=explicit_codes,
                        labels=tuple(
                            ICS_LABELS[code]
                            for code in explicit_codes
                        ),
                        method=str(
                            rec.get("classification_method", "indexed_sector_codes")
                        ),
                        confidence=confidence,
                    )
                elif explicit_code in ICS_TOP_LEVEL_LABELS:
                    confidence = str(
                        rec.get("classification_confidence", "high")
                    ).strip()
                    if confidence not in {"high", "medium", "low"}:
                        confidence = "low"
                    classification = SectorClassification(
                        source_sector=source_sector,
                        codes=(explicit_code,),
                        labels=(ICS_TOP_LEVEL_LABELS[explicit_code],),
                        method=str(
                            rec.get("classification_method", "indexed_sector_code")
                        ),
                        confidence=confidence,
                    )
                elif explicit_code == OTHER_SECTOR_CODE:
                    classification = SectorClassification(
                        source_sector=source_sector or OTHER_SECTOR_LABEL,
                        codes=(),
                        labels=(),
                        method=str(
                            rec.get("classification_method", "indexed_unclassified")
                        ),
                        confidence="low",
                    )
                else:
                    classification = classify_sector(
                        source_sector,
                        title=rec.get("title", ""),
                        summary=rec.get("summary", ""),
                        keywords=rec.get("keywords", []),
                    )
                if self.sector_provenance == "legacy_keyword" and not explicit_code:
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
            fetched_at=datetime.now(timezone.utc),
            org_name=rec.get("institute") or self.org_default,
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
        semantic_context = filters.get("_semantic_context")
        if not isinstance(semantic_context, SemanticQueryContext):
            semantic_context = SemanticQueryContext(query=q)
        sector_filters = [s.strip() for s in (filters.get("sector") or "").split(",") if s.strip()]

        matched: list[tuple[dict, float]] = []
        semantic_evidence: list[tuple[dict, float]] = []
        for rec in self._records:
            classification = rec["_sector_classification"]
            if not matches_sector_filter(classification, sector_filters):
                continue
            if q:
                is_match, score, semantic_score = semantic_search.score_record(
                    rec,
                    semantic_context,
                    self.id,
                )
                if not is_match:
                    continue
                matched.append((rec, score))
                if semantic_score:
                    semantic_evidence.append((rec, semantic_score))
            else:
                matched.append((rec, 0.0))

        if q and semantic_context.available:
            matched.sort(
                key=lambda item: (
                    item[1],
                    item[0].get("title", "").lower(),
                ),
                reverse=True,
            )
            semantic_search.learn_from_matches(q, semantic_evidence)

        total = len(matched)
        page_slice = matched[(page - 1) * page_size: page * page_size]
        return [self._to_technology(record) for record, _ in page_slice], total

    def sector_facets(self) -> dict[str, int]:
        self._load()
        counts: dict[str, int] = {}
        for rec in self._records:
            classification = rec["_sector_classification"]
            codes = top_level_sector_codes(classification) or (OTHER_SECTOR_CODE,)
            for code in codes:
                counts[code] = counts.get(code, 0) + 1
        return counts

    def facet_records(self):
        self._load()
        for rec in self._records:
            yield {
                "id": str(rec.get("id", "")),
                "record": rec,
                "searchable": searchable_text(rec).lower(),
                "classification": rec["_sector_classification"],
                "country": self.country,
            }

    def semantic_records(self) -> list[dict]:
        """Return loaded public metadata for the offline index builder."""
        self._load()
        return self._records

    def is_healthy(self) -> bool:
        return self._data_path.exists()
