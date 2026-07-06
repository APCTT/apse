"""
Crawl NRDC (National Research Development Corporation, India) technology
listings for licensing/commercialization.
Source: https://nrdcindia.com/ — 11 category pages, each linking to detail
pages with an "Area of Technology" (sector) field and a rich-text description.
Run: python -m backend.sources.crawl_nrdc
"""
import json
import re
import time
import httpx
from pathlib import Path
from bs4 import BeautifulSoup

OUTPUT = Path(__file__).parent / "data" / "nrdc_india.json"
BASE = "https://nrdcindia.com"

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
        items.append({"id": int(m.group(1)), "title": title, "href": a["href"]})
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

    email_match = re.search(r"Email:\s*([\w.+-]+@[\w-]+\.[\w.-]+)", text)
    contact_email = email_match.group(1) if email_match else ""

    return {
        "id": f"nrdc_{tech_id}",
        "title": title,
        "summary": summary,
        "sector": sector,
        "keywords": [],
        "institute": "National Research Development Corporation (NRDC)",
        "url": href,
        "contact_email": contact_email,
        "trl": "",
    }


def crawl():
    records = []
    seen_ids = set()
    with httpx.Client() as client:
        for cat_id, cat_name in CATEGORIES.items():
            print(f"Listing category {cat_id}: {cat_name} ...")
            try:
                items = list_category(client, cat_id)
            except Exception as e:
                print(f"  FAILED to list category {cat_id}: {e}")
                continue
            print(f"  {len(items)} technologies found")

            for item in items:
                if item["id"] in seen_ids:
                    continue
                seen_ids.add(item["id"])
                try:
                    rec = fetch_detail(client, item["id"], item["title"], cat_name, item["href"])
                except Exception as e:
                    print(f"  FAILED detail {item['id']}: {e}")
                    continue
                if rec:
                    records.append(rec)
                time.sleep(0.3)

            print(f"  Total records so far: {len(records)}")

    print(f"\nGrand total: {len(records)} technologies")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"Saved to {OUTPUT}")
    return records


if __name__ == "__main__":
    crawl()
