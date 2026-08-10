"""
Crawler: DOST-TAPI Philippines technology transfer portal
https://tapitechtransfer.dost.gov.ph/technologies

Run from the apctt-gateway directory:
    python scripts/crawl_dost_tapi.py

Requirements: httpx, beautifulsoup4
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.sources.crawler_safety import (
    print_snapshot_diff,
    resolve_output,
    validate_snapshot,
    write_json_atomic,
)
from backend.taxonomy.iso_ics import classify_sector

BASE = "https://tapitechtransfer.dost.gov.ph"
LIST_URL = f"{BASE}/technologies"
OUT_PATH = REPO_ROOT / "backend" / "sources" / "data" / "dost_tapi.json"
STAGING_PATH = OUT_PATH.with_name("dost_tapi.staging.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; APCTT-Gateway-Crawler/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}
CONCURRENCY = 4
DELAY = 0.5
MINIMUM_RECORDS = 65


CATEGORY_SLUGS = [
    "agricultural-productivity",
    "it-development",
    "msme-competitiveness",
    "quality-healthcare",
    "disaster-resilience",
]

CATEGORY_SECTORS = {
    "agricultural-productivity": ("Agricultural productivity", "65"),
    "it-development": ("IT development", "35"),
    "msme-competitiveness": ("MSME competitiveness", None),
    "quality-healthcare": ("Quality healthcare", "11"),
    "disaster-resilience": ("Disaster resilience", None),
}

# DOST's MSME and disaster-resilience groupings are programme themes rather
# than technology sectors. These 14 current records were reviewed individually
# against the ISO ICS top-level vocabulary instead of forcing the whole theme
# into one field.
DOST_REVIEWED_SECTOR_CODES = {
    "nipa-sugar": "67",
    "nanocoat-glass": "81",
    "coatin": "87",
    "clinn-gem": "73",
    "charm-charging-minutes": "43",
    "gitara-ni-juan": "97",
    "microbial-rennet-cheese-making": "67",
    "chevon-products-slaughtered-goats": "67",
    "fruitect-biocomposite-coating-fruits": "67",
    "universal-structural-health-evaluation-and-recording-usher": "93",
    "organomineral": "13",
    "geo-safer": "35",
    "remote-sensing-and-data-science-datos": "35",
    "unmanned-aerial-vehicles": "49",
}

async def _get_tech_urls_from_category(client: httpx.AsyncClient, cat_slug: str) -> list[str]:
    """Paginate a single category page and return individual tech URLs."""
    urls = []
    page = 0
    cat_url = f"{LIST_URL}/{cat_slug}"
    cat_prefix = f"{cat_url}/"

    while True:
        paged = f"{cat_url}?page={page}" if page > 0 else cat_url
        try:
            r = await client.get(paged, headers=HEADERS, timeout=30)
            r.raise_for_status()
        except Exception as e:
            raise RuntimeError(
                f"category {cat_slug} page {page} failed"
            ) from e

        soup = BeautifulSoup(r.text, "html.parser")
        found = []

        for a in soup.find_all("a", href=True):
            href = a["href"]
            full = urljoin(BASE, href)
            # Individual tech pages sit one level deeper than the category
            if full.startswith(cat_prefix) and "?" not in full and full not in urls:
                found.append(full)

        if not found:
            # Fallback: any /node/ links
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.match(r"^/node/\d+$", href):
                    full = urljoin(BASE, href)
                    if full not in urls and full not in found:
                        found.append(full)

        if not found:
            raise ValueError(
                f"category {cat_slug} page {page} contained no technology links"
            )

        urls.extend(found)
        print(f"    [{cat_slug}] page {page}: +{len(found)} techs (total {len(urls)})")

        next_link = soup.select_one("a[rel='next'], .pager__item--next a, li.next a")
        if not next_link:
            break
        page += 1
        await asyncio.sleep(DELAY)

    return list(dict.fromkeys(urls))


async def get_all_tech_urls(client: httpx.AsyncClient) -> list[str]:
    """Walk all 5 category pages and collect individual tech URLs."""
    all_urls = []
    for cat in CATEGORY_SLUGS:
        print(f"  Category: {cat}")
        cat_urls = await _get_tech_urls_from_category(client, cat)
        all_urls.extend(cat_urls)
        await asyncio.sleep(DELAY)
    return list(dict.fromkeys(all_urls))


def _source_category(url: str) -> tuple[str, str | None]:
    for slug, value in CATEGORY_SECTORS.items():
        if f"/technologies/{slug}/" in url:
            return value
    return "Other / Unclassified", None


def _extract_institute(soup: BeautifulSoup) -> str:
    profile = soup.select_one(".field--name-field-profile-of-technologist")
    if profile is None:
        return ""
    organization_terms = (
        "university", "institute", "college", "centre", "center",
        "laboratory", "department", "foundation", "corporation",
    )
    for paragraph in profile.find_all("p"):
        for line in paragraph.get_text("\n", strip=True).splitlines():
            candidate = " ".join(line.split()).strip(" ,;-")
            lowered = candidate.lower()
            if lowered.startswith("for inquiries"):
                break
            if "@" not in candidate and any(term in lowered for term in organization_terms):
                return candidate
    return ""


def parse_tech_page(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.get_text(" ", strip=True)

    # ID from URL slug
    slug = url.rstrip("/").split("/")[-1]
    tech_id = slug

    # Title
    title = ""
    for sel in ["h1.page-title", "h1.title", "h1", ".field--name-title", ".node__title"]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            title = el.get_text(strip=True)
            break
    if not title:
        title = soup.title.get_text(strip=True) if soup.title else slug.replace("-", " ").title()

    # Summary — body field paragraphs
    summary = ""
    for sel in [".field--name-body", ".field--name-field-description",
                ".field--name-field-technology-description", "article .field"]:
        el = soup.select_one(sel)
        if el:
            paras = [p.get_text(" ", strip=True) for p in el.find_all("p") if len(p.get_text(strip=True)) > 20]
            if paras:
                summary = " ".join(paras[:3])
                break
    if not summary:
        paras = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 30]
        summary = " ".join(paras[:3])

    # The structured profile identifies the proposing/developing institution.
    # DOST agencies mentioned later as inquiry contacts are intentionally not
    # treated as the technology provider.
    institute = _extract_institute(soup)

    # TRL
    trl = ""
    m_trl = re.search(r"TRL[-\s]*(\d)", body, re.IGNORECASE)
    if m_trl:
        trl = f"TRL-{m_trl.group(1)}"

    sector, sector_code = _source_category(url)
    classification_method = "dost_official_category_mapping"
    classification_confidence = "high"
    if slug in DOST_REVIEWED_SECTOR_CODES:
        sector_code = DOST_REVIEWED_SECTOR_CODES[slug]
        classification_method = "dost_reviewed_record_mapping"
        classification_confidence = "high"
    elif sector_code is None:
        classification = classify_sector("", title=title, summary=summary)
        sector_code = classification.codes[0] if classification.codes else "other"
        classification_method = "dost_content_fallback"
        classification_confidence = "low"

    # Keywords from slug
    stop = {"and", "the", "for", "with", "from", "into", "using", "based"}
    keywords = [w for w in slug.replace("-", " ").split() if len(w) > 3 and w not in stop]

    return {
        "id": f"dost_tapi_{tech_id}",
        "tech_id": tech_id,
        "title": title,
        "summary": summary[:800],
        "institute": institute,
        "trl": trl,
        "sector": sector,
        "sector_code": sector_code,
        "classification_method": classification_method,
        "classification_confidence": classification_confidence,
        "keywords": keywords[:10],
        "url": url,
    }


async def crawl_one(client: httpx.AsyncClient, url: str, idx: int, total: int) -> dict | None:
    for attempt in range(1, 4):
        try:
            r = await client.get(url, headers=HEADERS, timeout=25)
            r.raise_for_status()
            rec = parse_tech_page(r.text, url)
            print(f"  [{idx}/{total}] {rec['title'][:70]}")
            return rec
        except Exception as exc:
            if attempt == 3:
                print(f"  [{idx}/{total}] FAILED after 3 attempts {url} — {exc}")
                return None
            await asyncio.sleep(attempt)
    return None


async def run(args: argparse.Namespace):
    output = resolve_output(args.output, OUT_PATH, args.replace_production)
    results = []
    failed = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        print("=== DOST-TAPI Philippines Crawler ===")
        urls = await get_all_tech_urls(client)
        total = len(urls)
        print(f"\nFound {total} technology URLs. Crawling detail pages…\n")

        for i in range(0, total, CONCURRENCY):
            batch = urls[i:i + CONCURRENCY]
            tasks = [crawl_one(client, u, i + j + 1, total) for j, u in enumerate(batch)]
            records = await asyncio.gather(*tasks)
            failed += sum(record is None for record in records)
            results.extend([r for r in records if r])
            await asyncio.sleep(DELAY)

    errors = validate_snapshot(
        results,
        minimum_records=args.minimum_records,
        discovered_count=total,
        failed_count=failed,
        production_path=OUT_PATH,
        max_failure_rate=args.max_failure_rate,
    )
    if errors:
        raise ValueError("DOST-TAPI crawl failed validation: " + "; ".join(errors))

    print_snapshot_diff(results, OUT_PATH)
    write_json_atomic(results, output)
    print(f"\nDone. {len(results)}/{total} technologies saved to {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=STAGING_PATH)
    parser.add_argument("--replace-production", action="store_true")
    parser.add_argument("--minimum-records", type=int, default=MINIMUM_RECORDS)
    parser.add_argument("--max-failure-rate", type=float, default=0.05)
    return parser.parse_args()


def main() -> int:
    asyncio.run(run(parse_args()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
