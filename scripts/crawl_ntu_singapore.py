"""Build a reviewed snapshot of NTU Singapore's public Tech Offers catalogue.

The crawler reads the same public paginated listing endpoint used by the NTU
Tech Portal and visits each public detail page for its complete synopsis,
source categories, TRL and inventor names. It deliberately does not copy
images or contact details. The original NTU detail page remains authoritative.

The default output is a staging file. Replacing the production snapshot
requires both an explicit production path and ``--replace-production``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.sources.crawler_safety import (
    print_snapshot_diff,
    resolve_output,
    validate_snapshot,
    write_json_atomic,
)


CATALOGUE_URL = "https://www.ntu.edu.sg/innovates/tech-portal/tech-offers"
LISTING_ENDPOINT = f"{CATALOGUE_URL}/GetTechPortalServices/"
PRODUCTION_PATH = ROOT / "backend" / "sources" / "data" / "ntu_singapore.json"
STAGING_PATH = PRODUCTION_PATH.with_name("ntu_singapore.staging.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; APCTT-Gateway-Crawler/1.0)",
    "Accept": "text/html,application/json",
}
MINIMUM_RECORDS = 180

# Conservative mappings from NTU's public categories to the shared ISO ICS
# vocabulary. Broad cross-cutting categories retain at most two relevant codes;
# "Emerging Technologies" remains unclassified instead of being forced.
CATEGORY_TO_ICS = {
    "Additive Manufacturing": ("25",),
    "Artificial and Augmented Intelligence": ("35",),
    "Computer Networks and Communications": ("33", "35"),
    "Cyber Security and Privacy Preserving": ("35",),
    "Diagnostics": ("11",),
    "Drug Delivery Systems": ("11",),
    "Emerging Technologies": (),
    "Energy Efficiency and Storage Systems": ("27",),
    "Food, Agriculture and Aquaculture": ("65", "67"),
    "Intelligent Systems and Robotics": ("25", "35"),
    "Medical Devices": ("11",),
    "Microelectronics, Optoelectronics and Sensors": ("31",),
    "Nanotechnology and Materials Science": ("07",),
    "Semiconductors Engineering": ("31",),
    "Smart Mobility Adoption": ("43", "35"),
    "Sustainability and Clean Environment": ("13",),
    "Therapeutics": ("11",),
}


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _stable_id(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"ntu_singapore_{digest}"


def _split_categories(value: object) -> list[str]:
    if isinstance(value, list):
        candidates = value
    else:
        candidates = re.split(r"\s*\|\s*", str(value or ""))
    return list(dict.fromkeys(_clean_text(item) for item in candidates if _clean_text(item)))


def _sector_codes(categories: list[str]) -> list[str]:
    codes: list[str] = []
    for category in categories:
        for code in CATEGORY_TO_ICS.get(category, ()):
            if code not in codes:
                codes.append(code)
            if len(codes) == 3:
                return codes
    return codes


def _keywords(title: str, categories: list[str]) -> list[str]:
    stop = {
        "and", "the", "for", "from", "with", "using", "based", "technology",
        "technologies", "system", "method", "novel",
    }
    title_terms = [
        word
        for word in re.findall(r"[a-z0-9]+", title.lower())
        if len(word) > 2 and word not in stop
    ]
    return list(dict.fromkeys([*categories, *title_terms]))[:16]


def parse_listing(payload: object) -> tuple[list[dict], int, int]:
    if not isinstance(payload, dict):
        raise ValueError("NTU listing response is not an object")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("NTU listing response has no items array")
    total_items = int(payload.get("totalItems") or 0)
    total_pages = int(payload.get("totalPages") or 0)
    return [item for item in items if isinstance(item, dict)], total_items, total_pages


def parse_detail(html: str, listing: dict) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    detail = soup.select_one(".techportal-detail")
    if detail is None:
        raise ValueError("NTU technology detail container was not found")

    title = _clean_text(
        (detail.select_one(".detail-header__title") or {}).get_text(" ", strip=True)
        if detail.select_one(".detail-header__title")
        else listing.get("title")
    )
    summary_node = detail.select_one(".techportal-detail__overview")
    summary = _clean_text(
        summary_node.get_text(" ", strip=True) if summary_node else listing.get("description")
    )
    url = _clean_text(listing.get("url"))
    if not title or not summary or not url:
        raise ValueError("NTU detail is missing title, synopsis or URL")

    categories = [
        _clean_text(link.get_text(" ", strip=True))
        for link in detail.select(".article-detail__tags a")
    ]
    categories = list(dict.fromkeys(category for category in categories if category))
    if not categories:
        categories = _split_categories(listing.get("tag"))

    trl_node = detail.select_one("#gaugeValueDesktop, #gaugeValueMobile")
    trl_value = _clean_text(trl_node.get("value")) if trl_node else ""
    trl = f"TRL {trl_value}" if trl_value in {str(value) for value in range(1, 10)} else ""

    inventors: list[str] = []
    for group in detail.select(".az-listing__group"):
        heading = group.select_one(".az-listing__group-title")
        if heading and _clean_text(heading.get_text(" ", strip=True)).casefold() == "inventor":
            inventors.extend(
                _clean_text(node.get_text(" ", strip=True))
                for node in group.select(".contact-widget__title")
            )
    inventors = list(dict.fromkeys(name for name in inventors if name))

    codes = _sector_codes(categories)
    source_sector = " | ".join(categories) or "Other / Unclassified"
    search_text = " ".join(
        part for part in (summary, source_sector, " ".join(inventors)) if part
    )
    return {
        "id": _stable_id(url),
        "title": title,
        "summary": summary,
        "search_text": search_text,
        "institute": "Nanyang Technological University (NTU Singapore)",
        "trl": trl,
        "reg_date": _clean_text(listing.get("date")),
        "sector": source_sector,
        "sector_codes": codes,
        "sector_code": "other" if not codes else "",
        "classification_method": (
            "ntu_category_mapping" if codes else "ntu_unclassified_category"
        ),
        "classification_confidence": "high" if codes else "low",
        "keywords": _keywords(title, categories),
        "inventors": inventors,
        "url": url,
    }


async def _fetch_json(client: httpx.AsyncClient, page: int) -> object:
    response = await client.get(
        LISTING_ENDPOINT,
        params={"page": page},
        headers=HEADERS,
        timeout=45,
    )
    response.raise_for_status()
    return response.json()


async def fetch_listings(client: httpx.AsyncClient) -> list[dict]:
    first_items, total_items, total_pages = parse_listing(await _fetch_json(client, 1))
    if total_items < MINIMUM_RECORDS or total_pages < 1:
        raise ValueError(
            f"unexpected NTU catalogue size: totalItems={total_items}, totalPages={total_pages}"
        )
    pages = await asyncio.gather(
        *(_fetch_json(client, page) for page in range(2, total_pages + 1))
    )
    items = list(first_items)
    for payload in pages:
        page_items, page_total, _ = parse_listing(payload)
        if page_total != total_items:
            raise ValueError("NTU catalogue total changed during pagination")
        items.extend(page_items)

    by_url = {
        _clean_text(item.get("url")): item
        for item in items
        if _clean_text(item.get("url"))
    }
    if len(by_url) != total_items:
        raise ValueError(
            f"NTU pagination returned {len(by_url)} unique URLs for {total_items} items"
        )
    return list(by_url.values())


async def _fetch_detail(
    client: httpx.AsyncClient,
    listing: dict,
    semaphore: asyncio.Semaphore,
    delay: float,
) -> tuple[dict | None, str | None]:
    url = _clean_text(listing.get("url"))
    if urlparse(url).scheme != "https" or urlparse(url).netloc != "www.ntu.edu.sg":
        return None, f"invalid NTU detail URL: {url}"
    async with semaphore:
        if delay:
            await asyncio.sleep(delay)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await client.get(url, headers=HEADERS, timeout=45)
                response.raise_for_status()
                return parse_detail(response.text, listing), None
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
        return None, f"{url}: {last_error}"


async def run(
    output: Path,
    minimum: int,
    replace_production: bool,
    concurrency: int,
    delay: float,
) -> list[dict]:
    resolved = resolve_output(output, PRODUCTION_PATH, replace_production)
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(follow_redirects=True, limits=limits) as client:
        listings = await fetch_listings(client)
        semaphore = asyncio.Semaphore(concurrency)
        outcomes = await asyncio.gather(
            *(_fetch_detail(client, item, semaphore, delay) for item in listings)
        )

    records = [record for record, _ in outcomes if record is not None]
    failures = [error for _, error in outcomes if error]
    records.sort(key=lambda record: record["title"].casefold())
    errors = validate_snapshot(
        records,
        minimum_records=minimum,
        discovered_count=len(listings),
        failed_count=len(failures),
        production_path=PRODUCTION_PATH,
        max_failure_rate=0.03,
    )
    if errors:
        preview = "; ".join(failures[:3])
        raise ValueError(
            "NTU crawl failed validation: " + "; ".join(errors)
            + (f"; sample failures: {preview}" if preview else "")
        )

    print_snapshot_diff(records, PRODUCTION_PATH)
    write_json_atomic(records, resolved)
    print(
        f"Saved {len(records)} NTU technology offers to {resolved}; "
        f"detail failures={len(failures)}"
    )
    for category, count in sorted(
        Counter(record["sector"] for record in records).items()
    ):
        print(f"  {category}: {count}")
    if failures:
        print("Detail failures:")
        for failure in failures:
            print(f"  {failure}")
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=STAGING_PATH)
    parser.add_argument("--minimum", type=int, default=MINIMUM_RECORDS)
    parser.add_argument("--replace-production", action="store_true")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.concurrency <= 8:
        raise ValueError("--concurrency must be between 1 and 8")
    if args.delay < 0:
        raise ValueError("--delay cannot be negative")
    asyncio.run(
        run(
            args.output,
            args.minimum,
            args.replace_production,
            args.concurrency,
            args.delay,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
