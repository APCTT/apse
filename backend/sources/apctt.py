"""Live APCTT Drupal REST Export integration."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone

import httpx

from backend.models.technology import Technology
from backend.search.semantic import SemanticQueryContext, searchable_text, semantic_search
from backend.sources.base import BaseSource
from backend.taxonomy.apctt_taxonomy import (
    APCTT_COUNTRY_TID_TO_NAME,
    APCTT_SECTOR_TID_LABELS,
    APCTT_SECTOR_TID_TO_ICS,
)
from backend.taxonomy.iso_ics import (
    ICS_TOP_LEVEL_LABELS,
    OTHER_SECTOR_CODE,
    OTHER_SECTOR_LABEL,
    SectorClassification,
    TAXONOMY_SCHEME,
    TAXONOMY_VERSION,
    matches_sector_filter,
)

logger = logging.getLogger(__name__)


class APCTTSource(BaseSource):
    id = "apctt"
    name = "APCTT Technology Offers"
    country = "Asia and the Pacific"
    institution = "Asian and Pacific Centre for Transfer of Technology (APCTT)"
    status = "Metadata search"
    url = "https://www.apctt.org/technology-offers"
    ttl_seconds = 3600
    transfer_type = "Technology transfer / cooperation"
    sector_filter_supported = True
    facet_count_supported = True
    requires_facet_preparation = True
    multi_country = True

    _API_URL = "https://www.apctt.org/api/technology-offers"
    _MAX_PAGES = 100
    _PAGE_SIZE = 20

    def __init__(self):
        self._records: list[dict] = []
        self._cache_expires_at = 0.0
        self._lock: asyncio.Lock | None = None

    async def _request_page(self, page: int) -> list[dict]:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                self._API_URL,
                params={"_format": "json", "page": page},
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AP-Tech-Gateway/1.0",
                },
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("APCTT API returned a non-list response")
        return [item for item in payload if isinstance(item, dict)]

    async def _load(self) -> None:
        if self._records and time.monotonic() < self._cache_expires_at:
            return
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if self._records and time.monotonic() < self._cache_expires_at:
                return

            records: list[dict] = []
            seen_ids: set[str] = set()
            try:
                for page in range(self._MAX_PAGES):
                    raw_page = await self._request_page(page)
                    if not raw_page:
                        break
                    added = 0
                    for raw_record in raw_page:
                        record = self._normalize_record(raw_record)
                        if not record or record["id"] in seen_ids:
                            continue
                        seen_ids.add(record["id"])
                        records.append(record)
                        added += 1
                    # The current Drupal View ignores `page` and repeats page 0.
                    # Stopping when a page adds nothing prevents duplicate records,
                    # while still supporting normal View pagination if enabled later.
                    if added == 0:
                        break
            except Exception:
                if self._records:
                    # Keep serving the last successful catalogue during a brief
                    # upstream outage, but retry soon instead of waiting an hour.
                    self._cache_expires_at = time.monotonic() + 60
                    logger.warning("APCTT: refresh failed; serving stale catalogue")
                    return
                raise

            self._records = records
            self._cache_expires_at = time.monotonic() + self.ttl_seconds
            logger.info("APCTT: loaded %d unique technology offers", len(records))

    async def prepare_facets(self) -> None:
        await self._load()

    async def search(self, query: str, filters: dict) -> tuple[list[Technology], int]:
        await self._load()
        page = int(filters.get("page", 1))
        selected_countries = {
            value.strip()
            for value in (filters.get("country") or "").split(",")
            if value.strip()
        }
        selected_sectors = [
            value.strip()
            for value in (filters.get("sector") or "").split(",")
            if value.strip()
        ]
        normalized_query = query.strip().lower()
        semantic_context = filters.get("_semantic_context")
        if not isinstance(semantic_context, SemanticQueryContext):
            semantic_context = SemanticQueryContext(query=normalized_query)

        matched: list[tuple[dict, float]] = []
        semantic_evidence: list[tuple[dict, float]] = []
        for record in self._records:
            if selected_countries and not selected_countries.intersection(record["countries"]):
                continue
            if not matches_sector_filter(record["classification"], selected_sectors):
                continue
            if normalized_query:
                is_match, score, semantic_score = semantic_search.score_record(
                    record["search_record"], semantic_context, self.id
                )
                if not is_match:
                    continue
                matched.append((record, score))
                if semantic_score:
                    semantic_evidence.append((record["search_record"], semantic_score))
            else:
                matched.append((record, 0.0))

        if normalized_query and semantic_context.available:
            matched.sort(
                key=lambda item: (item[1], item[0]["title"].lower()),
                reverse=True,
            )
            semantic_search.learn_from_matches(normalized_query, semantic_evidence)

        total = len(matched)
        start = (page - 1) * self._PAGE_SIZE
        items = [self._to_technology(record) for record, _ in matched[start:start + self._PAGE_SIZE]]
        return items, total

    def facet_records(self):
        for record in self._records:
            yield {
                "id": record["id"],
                "record": record["search_record"],
                "searchable": searchable_text(record["search_record"]).lower(),
                "classification": record["classification"],
                "countries": record["countries"],
            }

    def _normalize_record(self, raw: dict) -> dict | None:
        nid = self._first_value(raw, "nid")
        title = self._clean_text(self._first_value(raw, "title"))
        if not nid or not title or not self._is_published(raw):
            return None

        country_tids = self._target_ids(raw, "field_country")
        countries = tuple(
            dict.fromkeys(
                APCTT_COUNTRY_TID_TO_NAME[tid]
                for tid in country_tids
                if tid in APCTT_COUNTRY_TID_TO_NAME
            )
        )
        if not countries:
            countries = ("Unspecified",)

        sector_tids = self._target_ids(raw, "field_page_sectors")
        source_sector_labels = tuple(
            APCTT_SECTOR_TID_LABELS[tid]
            for tid in sector_tids
            if tid in APCTT_SECTOR_TID_LABELS
        )
        sector_codes = tuple(
            dict.fromkeys(
                code
                for tid in sector_tids
                if (code := APCTT_SECTOR_TID_TO_ICS.get(tid))
                and code != OTHER_SECTOR_CODE
            )
        )
        classification = SectorClassification(
            source_sector=", ".join(source_sector_labels),
            codes=sector_codes,
            labels=tuple(ICS_TOP_LEVEL_LABELS[code] for code in sector_codes),
            method="apctt_taxonomy_tid" if source_sector_labels else "unclassified",
            confidence="high" if source_sector_labels else "low",
        )

        description = self._clean_text(
            self._first_value(raw, "field_web_resource_description_")
        )
        body = self._clean_text(self._first_value(raw, "body"))
        benefits = self._clean_text(self._first_value(raw, "field_benefits_advantages"))
        applications = self._clean_text(self._first_value(raw, "field_areas_of_application"))
        cooperation = self._clean_text(self._first_value(raw, "field_cooperation_sought"))
        summary = description or body or benefits or applications
        keywords = [
            self._clean_text(item.get("value"))
            for item in raw.get("field_keywords_maximum_5_", [])
            if isinstance(item, dict) and self._clean_text(item.get("value"))
        ]
        institute = self._clean_text(self._first_value(raw, "field_name_of_organization"))
        language = self._clean_text(self._first_value(raw, "langcode")) or "en"
        created = self._clean_text(self._first_value(raw, "created"))
        trl = self._format_trl(
            self._clean_text(self._first_value(raw, "field_technology_readiness_level"))
        )
        record_url = self._record_url(raw, str(nid))
        search_summary = " ".join(
            value for value in (summary, body, benefits, applications, cooperation) if value
        )
        search_record = {
            "id": f"apctt_{nid}",
            "title": title,
            "summary": search_summary,
            "institute": institute,
            "keywords": keywords,
        }
        return {
            "id": f"apctt_{nid}",
            "title": title,
            "summary": summary,
            "keywords": keywords,
            "institute": institute,
            "language": language,
            "countries": countries,
            "classification": classification,
            "trl": trl,
            "created": created[:10],
            "url": record_url,
            "search_record": search_record,
        }

    def _to_technology(self, record: dict) -> Technology:
        classification = record["classification"]
        return Technology(
            id=record["id"],
            title=record["title"],
            summary=record["summary"],
            sector=classification.primary_label,
            language=record["language"],
            keywords=record["keywords"],
            country=", ".join(record["countries"]),
            source_id=self.id,
            source_name=self.name,
            url=record["url"],
            fetched_at=datetime.now(timezone.utc),
            org_name=record["institute"],
            transfer_type=self.transfer_type,
            dev_status=record["trl"],
            reg_date=record["created"],
            source_sector=classification.source_sector,
            sector_codes=list(classification.codes),
            sector_labels=list(classification.labels),
            taxonomy_scheme=TAXONOMY_SCHEME,
            taxonomy_version=TAXONOMY_VERSION,
            classification_method=classification.method,
            classification_confidence=classification.confidence,
        )

    @staticmethod
    def _first_value(raw: dict, field: str):
        values = raw.get(field) or []
        if not isinstance(values, list) or not values or not isinstance(values[0], dict):
            return ""
        return values[0].get("value", "")

    @staticmethod
    def _target_ids(raw: dict, field: str) -> tuple[int, ...]:
        target_ids = []
        for item in raw.get(field) or []:
            if not isinstance(item, dict):
                continue
            try:
                target_ids.append(int(item.get("target_id")))
            except (TypeError, ValueError):
                continue
        return tuple(target_ids)

    @staticmethod
    def _clean_text(value) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def _is_published(raw: dict) -> bool:
        status = APCTTSource._first_value(raw, "status")
        return status is True or str(status).lower() in {"1", "true"}

    @staticmethod
    def _format_trl(value: str) -> str:
        match = re.fullmatch(r"trl_(\d+)_(.+)", value)
        if not match:
            return value.replace("_", " ").strip().title() if value else ""
        description = match.group(2).replace("_", " ").strip().capitalize()
        return f"TRL {match.group(1)} — {description}"

    @staticmethod
    def _record_url(raw: dict, nid: str) -> str:
        paths = raw.get("path") or []
        if paths and isinstance(paths[0], dict):
            alias = str(paths[0].get("alias") or "").strip()
            if alias.startswith("/"):
                return f"https://www.apctt.org{alias}"
        return f"https://www.apctt.org/node/{nid}"

    def is_healthy(self) -> bool:
        return True
