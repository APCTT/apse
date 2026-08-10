"""
Crawl NRDC (National Research Development Corporation, India) technology
listings for licensing/commercialization.
Source: https://nrdcindia.com/ — 11 category pages, each linking to detail
pages with an "Area of Technology" (sector) field and a rich-text description.
Run: python -m backend.sources.crawl_nrdc
"""
import argparse
import re
import time
import httpx
from pathlib import Path
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup

from backend.sources.crawler_safety import (
    print_snapshot_diff,
    resolve_output,
    validate_snapshot,
    write_json_atomic,
)

OUTPUT = Path(__file__).parent / "data" / "nrdc_india.json"
STAGING_OUTPUT = OUTPUT.with_name("nrdc_india.staging.json")
BASE = "https://nrdcindia.com"
MINIMUM_RECORDS = 430

CATEGORIES = {
    1: "Agro & Food Processing",
    2: "Chemical and Allied",
    3: "Civil Engineering",
    4: "Coir",
    5: "Electrical & Electronics",
    6: "Engineering Sciences",
    7: "Glass & Ceramics",
    8: "Life Sciences",
    9: "Sericulture",
    10: "Herbal / Home / Personal / Hygiene Care",
    11: "Food & Millet",
}

HEADERS = {"User-Agent": "APCTT-TechGateway-Crawler/1.0 (research; contact tlo@apctt.org)"}


def list_category(client: httpx.Client, cat_id: int) -> list[dict]:
    resp = client.get(f"{BASE}/TechnologyLists/{cat_id}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    for a in soup.select('a[href*="technologyDetals/"]'):
        m = re.search(r"technologyDetals/(\d+)", a["href"])
        if not m:
            continue
        title = a.get_text(strip=True)
        if not title:
            continue
        # The site 404s on a bare /technologyDetals/{id} — the title slug in
        # the href is required, so keep the full URL as given.
        absolute_href = urljoin(f"{BASE}/", a["href"])
        items.append({
            "id": int(m.group(1)),
            "title": title,
            # NRDC emits raw titles containing spaces, ampersands, apostrophes,
            # and parentheses in href paths. Encode them before requesting;
            # otherwise valid detail pages return HTTP 400.
            "href": quote(absolute_href, safe=":/%"),
        })
    return items


def fetch_detail(client: httpx.Client, tech_id: int, fallback_title: str, category: str, href: str) -> dict | None:
    resp = client.get(href, headers=HEADERS, timeout=30, follow_redirects=True)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    content = soup.select_one(".pageContent.detail")
    if not content:
        return None

    text = content.get_text(separator=" ", strip=True)

    sector_match = re.search(r"Area of Technology:\s*([^\n]+?)(?:Title of the Innovation|$)", text)
    sector = sector_match.group(1).strip() if sector_match else category

    title_match = re.search(r"Title of the Innovation:\s*([^\n]+?)(?:Brief About Innovation|$)", text)
    title = title_match.group(1).strip() if title_match else fallback_title

    brief_match = re.search(r"Brief About Innovation\s*(.+?)(?:Contact for the Technology|Express Interest|$)", text, re.DOTALL)
    summary = brief_match.group(1).strip() if brief_match else text[:400]
    summary = re.sub(r"\s+", " ", summary)[:500]

    return {
        "id": f"nrdc_{tech_id}",
        "tech_id": str(tech_id),
        "title": title,
        "summary": summary,
        "sector": sector,
        "keywords": [],
        "institute": "National Research Development Corporation (NRDC)",
        "url": href,
        "trl": "",
    }


def crawl(args: argparse.Namespace):
    output = resolve_output(args.output, OUTPUT, args.replace_production)
    records = []
    seen_ids = set()
    failed = 0
    with httpx.Client() as client:
        for cat_id, cat_name in CATEGORIES.items():
            print(f"Listing category {cat_id}: {cat_name} ...")
            try:
                items = list_category(client, cat_id)
            except Exception as e:
                print(f"  FAILED to list category {cat_id}: {e}")
                raise RuntimeError(f"NRDC category {cat_id} listing failed") from e
            if not items:
                raise ValueError(f"NRDC category {cat_id} returned no technology links")
            print(f"  {len(items)} technologies found")

            for item in items:
                if item["id"] in seen_ids:
                    continue
                seen_ids.add(item["id"])
                rec = None
                for attempt in range(1, 4):
                    try:
                        rec = fetch_detail(
                            client, item["id"], item["title"], cat_name, item["href"]
                        )
                        if rec:
                            break
                    except Exception as exc:
                        if attempt == 3:
                            print(f"  FAILED detail {item['id']} after 3 attempts: {exc}")
                    time.sleep(attempt)
                if rec:
                    records.append(rec)
                else:
                    failed += 1
                time.sleep(0.3)

            print(f"  Total records so far: {len(records)}")

    total = len(seen_ids)
    errors = validate_snapshot(
        records,
        minimum_records=args.minimum_records,
        discovered_count=total,
        failed_count=failed,
        production_path=OUTPUT,
        max_failure_rate=args.max_failure_rate,
    )
    if errors:
        raise ValueError("NRDC crawl failed validation: " + "; ".join(errors))

    print(f"\nGrand total: {len(records)} technologies")
    print_snapshot_diff(records, OUTPUT)
    write_json_atomic(records, output)
    print(f"Saved to {output}")
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=STAGING_OUTPUT)
    parser.add_argument("--replace-production", action="store_true")
    parser.add_argument("--minimum-records", type=int, default=MINIMUM_RECORDS)
    parser.add_argument("--max-failure-rate", type=float, default=0.05)
    return parser.parse_args()


if __name__ == "__main__":
    crawl(parse_args())
