"""Build a reviewed snapshot of APCTT's public technology-offer catalogue.

The production API reads only the committed snapshot. This crawler runs
outside Render, writes a staging file by default, excludes contact details,
and requires an explicit flag before replacing the production snapshot.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.sources.crawler_safety import (
    print_snapshot_diff,
    resolve_output,
    validate_snapshot,
    write_json_atomic,
)
from backend.taxonomy.apctt_taxonomy import (
    APCTT_COUNTRY_TID_TO_NAME,
    APCTT_SECTOR_TID_LABELS,
    APCTT_SECTOR_TID_TO_ICS,
)
from backend.taxonomy.iso_ics import OTHER_SECTOR_CODE


API_URL = "https://www.apctt.org/api/technology-offers"
PRODUCTION_PATH = ROOT / "backend" / "sources" / "data" / "apctt.json"
STAGING_PATH = ROOT / "backend" / "sources" / "data" / "apctt.staging.json"
MINIMUM_RECORDS = 1
MAX_PAGES = 100

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; APCTT-Gateway-Crawler/1.0)",
}


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _first_value(raw: dict, field: str):
    values = raw.get(field) or []
    if not isinstance(values, list) or not values or not isinstance(values[0], dict):
        return ""
    return values[0].get("value", "")


def _target_ids(raw: dict, field: str) -> tuple[int, ...]:
    target_ids: list[int] = []
    for item in raw.get(field) or []:
        if not isinstance(item, dict):
            continue
        try:
            target_ids.append(int(item.get("target_id")))
        except (TypeError, ValueError):
            continue
    return tuple(target_ids)


def _is_published(raw: dict) -> bool:
    status = _first_value(raw, "status")
    return status is True or str(status).lower() in {"1", "true"}


def _format_trl(value: str) -> str:
    if value.strip().lower() in {"not_sure", "not sure", "unknown", "n/a"}:
        return ""
    match = re.fullmatch(r"trl_(\d+)_(.+)", value)
    if not match:
        return value.replace("_", " ").strip().title() if value else ""
    description = match.group(2).replace("_", " ").strip().capitalize()
    return f"TRL {match.group(1)} — {description}"


def _record_url(raw: dict, nid: str) -> str:
    paths = raw.get("path") or []
    if paths and isinstance(paths[0], dict):
        alias = str(paths[0].get("alias") or "").strip()
        if alias.startswith("/"):
            return f"https://www.apctt.org{alias}"
    return f"https://www.apctt.org/node/{nid}"


def normalize_record(raw: dict) -> dict | None:
    """Convert one Drupal export record into the reviewed snapshot schema."""
    nid = _first_value(raw, "nid")
    title = _clean_text(_first_value(raw, "title"))
    if not nid or not title or not _is_published(raw):
        return None

    country_tids = _target_ids(raw, "field_country")
    countries = list(
        dict.fromkeys(
            APCTT_COUNTRY_TID_TO_NAME[tid]
            for tid in country_tids
            if tid in APCTT_COUNTRY_TID_TO_NAME
        )
    ) or ["Unspecified"]

    sector_tids = _target_ids(raw, "field_page_sectors")
    sector_labels = list(
        dict.fromkeys(
            APCTT_SECTOR_TID_LABELS[tid]
            for tid in sector_tids
            if tid in APCTT_SECTOR_TID_LABELS
        )
    )
    sector_codes = list(
        dict.fromkeys(
            code
            for tid in sector_tids
            if (code := APCTT_SECTOR_TID_TO_ICS.get(tid))
            and code != OTHER_SECTOR_CODE
        )
    )

    description = _clean_text(_first_value(raw, "field_web_resource_description_"))
    body = _clean_text(_first_value(raw, "body"))
    benefits = _clean_text(_first_value(raw, "field_benefits_advantages"))
    applications = _clean_text(_first_value(raw, "field_areas_of_application"))
    cooperation = _clean_text(_first_value(raw, "field_cooperation_sought"))
    summary = description or body or benefits or applications
    search_text = " ".join(
        dict.fromkeys(
            value
            for value in (summary, body, benefits, applications, cooperation)
            if value
        )
    )
    keywords = [
        value
        for item in raw.get("field_keywords_maximum_5_") or []
        if isinstance(item, dict) and (value := _clean_text(item.get("value")))
    ]
    created = _clean_text(_first_value(raw, "created"))
    language = _clean_text(_first_value(raw, "langcode")) or "en"

    return {
        "id": f"apctt_{nid}",
        "tech_id": str(nid),
        "title": title,
        "summary": summary,
        "search_text": search_text,
        "institute": _clean_text(_first_value(raw, "field_name_of_organization")),
        "trl": _format_trl(
            _clean_text(_first_value(raw, "field_technology_readiness_level"))
        ),
        "sector": ", ".join(sector_labels),
        "sector_codes": sector_codes,
        "sector_code": sector_codes[0] if sector_codes else OTHER_SECTOR_CODE,
        "classification_method": (
            "apctt_taxonomy_tid" if sector_labels else "unclassified"
        ),
        "classification_confidence": "high" if sector_labels else "low",
        "keywords": keywords,
        "countries": countries,
        "language": language,
        "reg_date": created[:10],
        "url": _record_url(raw, str(nid)),
    }


async def fetch_page(
    client: httpx.AsyncClient,
    page: int,
    *,
    api_url: str = API_URL,
) -> list[dict]:
    response = await client.get(
        api_url,
        params={"_format": "json", "page": page},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("APCTT export returned a non-list response")
    return [item for item in payload if isinstance(item, dict)]


async def collect_records(
    client: httpx.AsyncClient,
    *,
    api_url: str = API_URL,
    max_pages: int = MAX_PAGES,
) -> tuple[list[dict], int, int]:
    records: list[dict] = []
    seen_raw_ids: set[str] = set()
    seen_record_ids: set[str] = set()
    discovered_count = 0
    failed_count = 0

    for page in range(max_pages):
        raw_page = await fetch_page(client, page, api_url=api_url)
        if not raw_page:
            break

        new_raw_records = 0
        for raw in raw_page:
            raw_id = str(_first_value(raw, "nid") or "").strip()
            identity = raw_id or repr(raw)
            if identity in seen_raw_ids:
                continue
            seen_raw_ids.add(identity)
            new_raw_records += 1
            if not _is_published(raw):
                continue
            discovered_count += 1
            record = normalize_record(raw)
            if record is None:
                failed_count += 1
                continue
            if record["id"] in seen_record_ids:
                continue
            seen_record_ids.add(record["id"])
            records.append(record)

        # The Drupal View has previously ignored `page` and repeated page 0.
        if new_raw_records == 0:
            break

    records.sort(key=lambda record: (record.get("reg_date", ""), record["id"]), reverse=True)
    return records, discovered_count, failed_count


async def run(
    output: Path,
    *,
    minimum: int = MINIMUM_RECORDS,
    replace_production: bool = False,
    api_url: str = API_URL,
) -> list[dict]:
    resolved_output = resolve_output(output, PRODUCTION_PATH, replace_production)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        records, discovered_count, failed_count = await collect_records(
            client, api_url=api_url
        )

    errors = validate_snapshot(
        records,
        minimum_records=minimum,
        discovered_count=discovered_count,
        failed_count=failed_count,
        production_path=PRODUCTION_PATH,
    )
    if errors:
        raise ValueError("APCTT crawl failed validation: " + "; ".join(errors))

    print_snapshot_diff(records, PRODUCTION_PATH)
    write_json_atomic(records, resolved_output)
    print(f"Saved {len(records)} APCTT records to {resolved_output}")
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=STAGING_PATH)
    parser.add_argument("--minimum", type=int, default=MINIMUM_RECORDS)
    parser.add_argument("--replace-production", action="store_true")
    parser.add_argument("--api-url", default=API_URL)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    asyncio.run(
        run(
            args.output,
            minimum=args.minimum,
            replace_production=args.replace_production,
            api_url=args.api_url,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
