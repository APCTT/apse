import asyncio
from typing import Optional

from fastapi import APIRouter, Query
from backend.sources.registry import SOURCES
from backend.models.technology import Source
from backend.search.semantic import semantic_search
from backend.taxonomy.iso_ics import (
    ICS_TOP_LEVEL_LABELS,
    OTHER_SECTOR_CODE,
    OTHER_SECTOR_LABEL,
    TAXONOMY_SCHEME,
    TAXONOMY_VERSION,
    matches_sector_filter,
    top_level_sector_codes,
)

router = APIRouter()


@router.get("/sources", response_model=list[Source])
def get_sources():
    return [s.to_source_model() for s in SOURCES]


@router.get("/facets")
async def get_facets(
    q: Optional[str] = Query(None, max_length=200),
    country: Optional[str] = Query(None, max_length=300),
    sector: Optional[str] = Query(None, max_length=300),
    source: Optional[str] = Query(None, max_length=300),
    database_type: Optional[str] = Query(None, max_length=100),
):
    """Query-aware facets derived only from locally indexed catalogues.

    Counts follow standard faceted-search behavior: each group applies the
    current query and selections from the other groups, but not its own
    selection. This keeps alternative values useful while filters are active.
    Live APIs are not called for counts unless a source explicitly provides a
    bounded, cached catalogue preparation step (currently APCTT only).
    """
    preparable = [source for source in SOURCES if source.requires_facet_preparation]
    preparation_results = await asyncio.gather(
        *[
            asyncio.wait_for(source.prepare_facets(), timeout=12.0)
            for source in preparable
        ],
        return_exceptions=True,
    )
    unavailable_prepared_sources = {
        source.id
        for source, result in zip(preparable, preparation_results)
        if isinstance(result, BaseException)
    }
    facet_available = {
        source.id: source.facet_count_supported
        and source.id not in unavailable_prepared_sources
        for source in SOURCES
    }

    transfer_types = sorted({s.transfer_type for s in SOURCES if s.transfer_type})
    query = (q or "").strip().lower()
    semantic_context = semantic_search.cached_query(query) if query else None
    selected_countries = _split_values(country)
    selected_sectors = list(_split_values(sector))
    selected_sources = _split_values(source)
    selected_database_types = _split_values(database_type)
    metadata_enabled = not selected_database_types or "Metadata search" in selected_database_types

    sector_counts = {code: 0 for code in ICS_TOP_LEVEL_LABELS}
    sector_counts[OTHER_SECTOR_CODE] = 0
    country_counts: dict[str, int | None] = {}
    for catalogue in SOURCES:
        if catalogue.multi_country:
            continue
        if facet_available[catalogue.id]:
            country_counts[catalogue.country] = 0
        else:
            country_counts.setdefault(catalogue.country, None)
    source_counts = {
        catalogue.id: 0 if facet_available[catalogue.id] else None
        for catalogue in SOURCES
    }

    if metadata_enabled:
        for catalogue in SOURCES:
            if catalogue.status != "Metadata search":
                continue
            if not facet_available[catalogue.id]:
                continue
            source_matches = not selected_sources or catalogue.id in selected_sources

            for record in catalogue.facet_records():
                record_countries = tuple(
                    record.get("countries")
                    or ([record["country"]] if record.get("country") else [catalogue.country])
                )
                for record_country in record_countries:
                    country_counts.setdefault(record_country, 0)
                if query:
                    if semantic_context and semantic_context.available:
                        is_match, _, _ = semantic_search.score_record(
                            record["record"],
                            semantic_context,
                            catalogue.id,
                        )
                        if not is_match:
                            continue
                    elif query not in record["searchable"]:
                        continue
                classification = record["classification"]
                sector_matches = matches_sector_filter(classification, selected_sectors)
                country_matches = (
                    not selected_countries
                    or bool(selected_countries.intersection(record_countries))
                )

                if source_matches and sector_matches:
                    for record_country in record_countries:
                        country_counts[record_country] = (
                            country_counts.get(record_country, 0) or 0
                        ) + 1
                if country_matches and sector_matches:
                    source_counts[catalogue.id] = source_counts.get(catalogue.id, 0) + 1
                if country_matches and source_matches:
                    parent_codes = top_level_sector_codes(classification)
                    if parent_codes:
                        for code in parent_codes:
                            sector_counts[code] += 1
                    else:
                        sector_counts[OTHER_SECTOR_CODE] += 1

    sectors = [
        {"value": code, "label": ICS_TOP_LEVEL_LABELS[code], "count": sector_counts[code]}
        for code in ICS_TOP_LEVEL_LABELS
        if sector_counts[code] > 0 or code in selected_sectors
    ]
    if (
        sector_counts[OTHER_SECTOR_CODE] > 0
        or OTHER_SECTOR_CODE in selected_sectors
    ):
        sectors.append({
            "value": OTHER_SECTOR_CODE,
            "label": OTHER_SECTOR_LABEL,
            "count": sector_counts[OTHER_SECTOR_CODE],
        })
    countries = [
        {"value": value, "label": value, "count": count}
        for value, count in sorted(country_counts.items())
    ]
    sources = [
        {"value": catalogue.id, "label": catalogue.name, "count": source_counts.get(catalogue.id)}
        for catalogue in SOURCES
    ]
    return {
        "taxonomy": {"scheme": TAXONOMY_SCHEME, "version": TAXONOMY_VERSION},
        "sectors": sectors,
        "countries": countries,
        "sources": sources,
        "transfer_types": transfer_types,
    }


def _split_values(value: Optional[str]) -> set[str]:
    return {item.strip() for item in (value or "").split(",") if item.strip()}
