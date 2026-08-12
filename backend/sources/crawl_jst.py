"""
Crawl JST (Japan Science and Technology Agency) patent list for licensing.
Source: https://www.jst.go.jp/chizai/en/patent_en.html
~400 patents from Japanese universities and public research institutes.
Run: python -m backend.sources.crawl_jst
"""
import json
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

OUTPUT = Path(__file__).parent / "data" / "jst_japan.json"
URL = "https://www.jst.go.jp/chizai/en/patent_en.html"

CATEGORY_MAP = {
    "NEW MATERIAL (ORGANIC": "Materials",
    "NEW MATERIAL (INORGANIC": "Materials",
    "SEMICONDUCTOR": "Electronics",
    "ELECTRONIC DEVICE": "Electronics",
    "MICRO": "Manufacturing",
    "NANOTECHNOLOGY": "Manufacturing",
    "MEASUREMENT": "Manufacturing",
    "OPTICS": "Manufacturing",
    "DRUG DISCOVERY": "Health/Medicine",
    "DIAGNOSIS": "Health/Medicine",
    "TREATMENT": "Health/Medicine",
    "MEDICAL": "Health/Medicine",
    "BIOTECHNOLOGY": "Agriculture/Biotechnology",
    "CHEMICAL ENGINEERING": "Energy/Environment",
    "SOFTWARE": "IT/Software",
    "ENERGY": "Energy/Environment",
    "GREEN": "Energy/Environment",
    "COMMUNICATION": "IT/Software",
    "MACHINE": "Manufacturing",
    "ROBOT": "Manufacturing",
}


def map_sector(categories: list[str]) -> str:
    text = " ".join(categories).upper()
    for key, sector in CATEGORY_MAP.items():
        if key in text:
            return sector
    return "Technology"


def crawl():
    print(f"Fetching {URL} ...")
    headers = {"User-Agent": "APCTT-TechGateway-Crawler/1.0 (research; contact tlo@apctt.org)"}
    resp = httpx.get(URL, headers=headers, timeout=30, follow_redirects=True)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    records = []

    # The page uses a table or definition-list structure per patent
    # Each row: Patent No | Title | Inventors | Related Links | Categories
    rows = soup.select("table tr")

    # Skip header row(s)
    data_rows = [r for r in rows if r.find("td")]

    for i, row in enumerate(data_rows):
        cols = row.find_all("td")
        if len(cols) < 3:
            continue

        pat_link = cols[0].find("a")
        patent_no = pat_link.get_text(strip=True) if pat_link else cols[0].get_text(strip=True)
        title = cols[1].get_text(strip=True) if len(cols) > 1 else ""
        inventors = cols[2].get_text(separator=", ", strip=True) if len(cols) > 2 else ""
        related = cols[3].get_text(separator=" ", strip=True) if len(cols) > 3 else ""
        categories_raw = cols[4].get_text(separator=",", strip=True) if len(cols) > 4 else ""

        if not title or not patent_no:
            continue

        categories = [c.strip() for c in categories_raw.split(",") if c.strip()]
        sector = map_sector(categories)

        # Prefer the official JST-hosted patent document. Rows for pending
        # applications have no document link and therefore return users to the
        # official JST patent listing instead.
        patent_url = (
            urljoin(URL, pat_link.get("href"))
            if pat_link and pat_link.get("href")
            else URL
        )

        records.append({
            "id": f"jst_{i+1:04d}",
            "title": title,
            "summary": f"Inventors: {inventors}. {related}".strip(". "),
            "sector": sector,
            "keywords": categories,
            "institute": "Japan Science and Technology Agency (JST)",
            "url": patent_url,
            "patent_no": patent_no,
            "trl": "",
        })

        if (i + 1) % 50 == 0:
            print(f"  Parsed {i+1} rows...")

    print(f"\nTotal records: {len(records)}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"Saved to {OUTPUT}")
    return records


if __name__ == "__main__":
    crawl()
