"""
One-time crawler: downloads all CSIR India technologies and saves to
backend/sources/data/csir_india.json

Run from the apctt-gateway directory:
    python scripts/crawl_csir.py

Requirements: httpx, beautifulsoup4  (pip install httpx beautifulsoup4)
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

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

BASE = "https://techindiacsir.anusandhan.net/online"
LIST_URL = f"{BASE}/Control.do?_tech="
OUT_PATH = REPO_ROOT / "backend" / "sources" / "data" / "csir_india.json"
STAGING_PATH = OUT_PATH.with_name("csir_india.staging.json")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; APCTT-Gateway-Crawler/1.0)"}
CONCURRENCY = 5      # parallel fetches
DELAY = 0.4          # seconds between batches
MINIMUM_RECORDS = 1600

CSIR_GROUP_TO_ICS = {
    "food, beverages, tobacco": "67",
    "environmental (clean tech.)": "13",
    "agriculture": "65",
    "chemistry, chemical processes": "71",
    "biological science": "07.080",
    "building materials, construction technologies, furniture etc.": "91",
    "drugs and pharmaceuticals": "11",
    "instrumentation, appliances, devices": "17",
    "electronics": "31",
    "metallurgy": "77",
    "energy": "27",
    "analytical techniques": "19",
    "medical devices and diagnostics": "11",
    "leather,textiles and related items": "59",
    "mining and minerals": "73",
    "computers and electronic data processing": "35",
    "mechanical": "25",
    "electrical": "29",
    "fuels and lubricants": "75",
    "communications": "33",
    "aerospace": "49",
    "transportation": "03",
    "physics": "07",
}


async def get_all_tech_urls(client: httpx.AsyncClient) -> list[str]:
    """Scrape the listing page for all *-T-*-tech.htm hrefs."""
    print("Fetching technology list…")
    r = await client.get(LIST_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"-T-\d+-tech\.htm$", href):
            # Make absolute
            if not href.startswith("http"):
                href = f"{BASE}/{href.lstrip('/')}"
            urls.append(href)
    print(f"Found {len(urls)} technology URLs")
    return list(dict.fromkeys(urls))  # deduplicate preserving order


def _clean(value: str) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def _profile_fields(soup: BeautifulSoup) -> dict[str, str]:
    fields: dict[str, str] = {}
    for row in soup.select("table.table tr"):
        caption = row.select_one(".tech_caption")
        value = row.select_one(".tech_data")
        if caption is None or value is None:
            continue
        label = _clean(caption.get_text(" ", strip=True)).rstrip(":").lower()
        fields[label] = _clean(value.get_text(" ", strip=True))
    return fields


def _institute(soup: BeautifulSoup) -> str:
    lab_image = soup.select_one('img[src*="img/lab/"]')
    if lab_image is None:
        return ""
    parent_text = _clean(lab_image.parent.parent.get_text(" ", strip=True))
    acronym = re.search(r"\[(CSIR[-–][A-Z0-9]+)\]", parent_text)
    if acronym:
        return acronym.group(1).replace("–", "-")
    return _clean(lab_image.get("alt", ""))


def _industrial_applications(soup: BeautifulSoup) -> list[str]:
    for box in soup.select(".box-info"):
        label = box.select_one(".label-primary")
        if label and "industrial applications" in label.get_text(" ", strip=True).lower():
            return list(dict.fromkeys(
                _clean(item.get_text(" ", strip=True))
                for item in box.select(".label-default")
                if _clean(item.get_text(" ", strip=True))
            ))
    return []


def _classify_profile(
    applications: list[str], title: str, summary: str
) -> tuple[str, str]:
    for application in applications:
        for group in re.findall(r"\[\s*([^\]]+?)\s*\]", application):
            code = CSIR_GROUP_TO_ICS.get(_clean(group).lower())
            if code:
                return code, "high"
    classification = classify_sector(
        "",
        title=title,
        summary=summary,
        keywords=applications,
    )
    if classification.codes:
        return classification.codes[0], "low"
    return "other", "low"


def parse_tech_page(html: str, url: str) -> dict:
    """Extract structured fields from an individual technology page."""
    soup = BeautifulSoup(html, "html.parser")
    # Tech ID from URL
    m = re.search(r"-T-(\d+)-tech\.htm", url)
    tech_id = m.group(1) if m else ""

    fields = _profile_fields(soup)
    title = fields.get("title", "")
    if not title:
        title = soup.title.get_text(strip=True) if soup.title else "Untitled"

    summary_parts = [
        fields.get("value proposition", ""),
        fields.get("summary application", ""),
        fields.get("advantages", ""),
    ]
    summary = _clean(" ".join(part for part in summary_parts if part))

    institute = _institute(soup)

    body_text = soup.get_text(" ")
    trl = ""
    m_trl = re.search(r"renderTo:\s*['\"]TRIGaugeDiv['\"][\s\S]+?data:\s*\[(\d)\]", html)
    if not m_trl:
        m_trl = re.search(r"TRL[-\s]*(\d)", body_text, re.IGNORECASE)
    if m_trl:
        trl = f"TRL-{m_trl.group(1)}"

    applications = _industrial_applications(soup)
    sector = "; ".join(applications)
    sector_code, classification_confidence = _classify_profile(
        applications, title, summary
    )

    # Keywords from slug
    slug_part = url.split("/")[-1].replace(f"-T-{tech_id}-tech.htm", "")
    keywords = [w for w in slug_part.replace("-", " ").split() if len(w) > 3]

    return {
        "id": f"csir_{tech_id}",
        "tech_id": tech_id,
        "title": title,
        "summary": summary[:800],
        "institute": institute,
        "trl": trl,
        "sector": sector,
        "sector_code": sector_code,
        "classification_method": "csir_industrial_application_mapping",
        "classification_confidence": classification_confidence,
        "keywords": keywords[:10],
        "url": url,
    }


async def crawl_one(client: httpx.AsyncClient, url: str, idx: int, total: int) -> dict | None:
    for attempt in range(1, 4):
        try:
            r = await client.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            record = parse_tech_page(r.text, url)
            if idx == 1 or idx == total or idx % 50 == 0:
                print(f"  [{idx}/{total}] {record['title'][:60]}")
            return record
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
        urls = await get_all_tech_urls(client)
        total = len(urls)

        # Process in batches of CONCURRENCY
        for i in range(0, total, CONCURRENCY):
            batch = urls[i:i + CONCURRENCY]
            tasks = [crawl_one(client, url, i + j + 1, total) for j, url in enumerate(batch)]
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
        raise ValueError("CSIR crawl failed validation: " + "; ".join(errors))

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
