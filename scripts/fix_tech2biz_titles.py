"""
Fix tech2biz.json titles — re-crawls the 41 listing pages to extract correct
Thai titles (h5 inside card links), translates them, and patches the JSON.

Run from the apctt-gateway directory:
    python scripts/fix_tech2biz_titles.py
"""

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

BASE = "https://www.tech2biz.net"
LIST_URL = f"{BASE}/content/inventor"
OUT_PATH = Path(__file__).parent.parent / "backend" / "sources" / "data" / "tech2biz.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; APCTT-Gateway-Crawler/1.0)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
}


def extract_id(url: str) -> str:
    m = re.search(r"/content/(\d+)-", url)
    return m.group(1) if m else ""


async def translate_th_en(client: httpx.AsyncClient, text: str) -> str:
    if not text or not text.strip():
        return text
    try:
        r = await client.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text[:400], "langpair": "th|en"},
            timeout=10,
        )
        data = r.json()
        translated = data.get("responseData", {}).get("translatedText", "")
        response_status = data.get("responseStatus")
        error_text = f"{translated} {data.get('responseDetails', '')}".upper()
        is_error = any(marker in error_text for marker in (
            "MYMEMORY WARNING",
            "YOU USED ALL AVAILABLE FREE TRANSLATIONS",
            "NEXT AVAILABLE IN",
            "QUERY LENGTH LIMIT EXCEEDED",
        ))
        if (
            response_status in (None, 200, "200")
            and translated
            and not is_error
            and translated.lower() != text.lower()
        ):
            return translated
    except Exception:
        pass
    return text


async def get_listing_titles(client: httpx.AsyncClient, page: int) -> dict[str, str]:
    """Return {tech_id: thai_title} for all items on this listing page."""
    url = f"{LIST_URL}?page={page}" if page > 1 else LIST_URL
    r = await client.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    result = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not re.match(r"^/content/\d+-", href):
            continue
        tech_id = extract_id(href)
        if not tech_id:
            continue
        h5 = a.find("h5")
        if h5:
            title = h5.get_text(strip=True)
            if title:
                result[tech_id] = title
    return result


async def main():
    print("=== Tech2Biz Title Fix ===")

    # Load existing JSON
    with open(OUT_PATH, encoding="utf-8") as f:
        records = json.load(f)

    id_to_record = {r["tech_id"]: r for r in records}
    print(f"Loaded {len(records)} existing records")

    # Re-crawl listing pages to get correct Thai titles
    print("\nStep 1: Re-crawling 41 listing pages for correct titles...")
    id_to_thai_title = {}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for page in range(1, 42):
            titles = await get_listing_titles(client, page)
            id_to_thai_title.update(titles)
            print(f"  Page {page}/41: +{len(titles)} titles (total {len(id_to_thai_title)})")
            await asyncio.sleep(0.5)

        print(f"\nStep 2: Translating {len(id_to_thai_title)} titles...")
        id_to_en_title = {}
        items = list(id_to_thai_title.items())
        for i, (tech_id, thai_title) in enumerate(items):
            en_title = await translate_th_en(client, thai_title)
            id_to_en_title[tech_id] = en_title
            if (i + 1) % 50 == 0:
                print(f"  Translated {i + 1}/{len(items)}")
            await asyncio.sleep(0.4)

    # Patch records
    patched = 0
    for rec in records:
        tid = rec["tech_id"]
        if tid in id_to_en_title:
            rec["title"] = id_to_en_title[tid]
            patched += 1

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"\nDone. Patched {patched}/{len(records)} titles.")
    for rec in records[:5]:
        print(f"  • [{rec['sector']}] {rec['title'][:70]}")


if __name__ == "__main__":
    asyncio.run(main())
