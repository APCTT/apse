from typing import Optional

from fastapi import APIRouter, Query
from backend.sources.registry import SOURCES
from backend.models.technology import Source
from backend.search.semantic import semantic_search
from backend.taxonomy.iso_ics import (
    ICS_LABELS,
    TAXONOMY_SCHEME,
    TAXONOMY_VERSION,
    matches_sector_filter,
)

router = APIRouter()


@router.get("/sources", response_model=list[Source])
def get_sources():
    return [s.to_source_model() for s in SOURCES]


@router.get("/facets")
def get_facets(
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
    Live APIs are never called to calculate these counts.
    """
    transfer_types = sorted({s.transfer_type for s in SOURCES if s.transfer_type})
    query = (q or "").strip().lower()
    semantic_context = semantic_search.cached_query(query) if query else None
    selected_countries = _split_values(country)
    selected_sectors = list(_split_values(sector))
    selected_sources = _split_values(source)
    selected_database_types = _split_values(database_type)
    metadata_enabled = not selected_database_types or "Metadata search" in selected_database_types

    sector_counts = {code: 0 for code in ICS_LABELS}
    country_counts: dict[str, int | None] = {}
    for catalogue in SOURCES:
        if catalogue.facet_count_supported:
            country_counts[catalogue.country] = 0
        else:
            country_counts.setdefault(catalogue.country, None)
    source_counts = {
        catalogue.id: 0 if catalogue.facet_count_supported else None
        for catalogue in SOURCES
    }

    if metadata_enabled:
        for catalogue in SOURCES:
            if catalogue.status != "Metadata search":
                continue
            country_matches = not selected_countries or catalogue.country in selected_countries
            source_matches = not selected_sources or catalogue.id in selected_sources

            for record in catalogue.facet_records():
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

                if source_matches and sector_matches:
                    country_counts[catalogue.country] = country_counts.get(catalogue.country, 0) + 1
                if country_matches and sector_matches:
                    source_counts[catalogue.id] = source_counts.get(catalogue.id, 0) + 1
                if country_matches and source_matches:
                    for code in classification.codes:
                        if code in sector_counts:
                            sector_counts[code] += 1

    sectors = [
        {"value": code, "label": ICS_LABELS[code], "count": count}
        for code, count in sorted(sector_counts.items(), key=lambda item: item[0])
    ]
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
