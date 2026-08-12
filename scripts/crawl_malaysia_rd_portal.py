"""Build a reviewed snapshot of Malaysia's public R&D product catalogue.

The Malaysian R&D Commercialisation Portal loads its public showcase from a
Firebase Realtime Database. This crawler reads the same public collection used
by the portal, removes duplicate title/provider pairs, and deliberately omits
business email and address fields from the APTG snapshot. Users are directed
to the original portal record for current details and contact information.

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
from urllib.parse import quote, urlparse

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


PORTAL_URL = "https://commercialisation.mosti.gov.my/rd-products"
DATA_URL = (
    "https://mranti-commercialisation-default-rtdb.asia-southeast1."
    "firebasedatabase.app/products.json"
)

PRODUCTION_PATH = ROOT / "backend" / "sources" / "data" / "malaysia_rd_portal.json"
STAGING_PATH = ROOT / "backend" / "sources" / "data" / "malaysia_rd_portal.staging.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; APCTT-Gateway-Crawler/1.0)",
    "Accept": "application/json",
}

MINIMUM_RECORDS = 900
NON_ASCII_RUN = re.compile(r"[^\x00-\x7f]+")

# Conservative mappings from the portal's own categories to the shared ISO
# ICS vocabulary. A record may retain up to three distinct sector codes, which
# matches the existing fallback classifier's cross-sector limit.
CATEGORY_TO_ICS = {
    "Agriculture": ("65",),
    "Renewable Energy": ("27",),
    "Lifestyle & Fashion": ("61",),
    "Consulting & Services": ("03",),
    "E-Commerce": ("35",),
    "Education": ("03",),
    "Entertainment": ("97",),
    "Finance and Banking": ("03",),
    "Food & Beverages": ("67",),
    "Gaming": ("35", "97"),
    "Medical and Healthcare": ("11",),
    "Automotive": ("43",),
    "Aerospace": ("49",),
    "Biotechnology": ("07.080",),
    "Chemicals and Petrochemicals": ("71", "75"),
    "Real Estate": ("03",),
    "Tourism and Hospitality": ("03",),
    "Construction": ("91", "93"),
    "Information Technology (IT) and Business Process Outsourcing (BPO)": ("35",),
    "Legal and Law": ("03",),
    "Media and Entertainment": ("33",),
    "Sports & Recreation": ("97",),
    "Logistic and Transportation": ("03",),
    "Jobs & HR": ("03",),
    "Event Marketing & Advertising": ("03",),
    "Environmental and Green Technology": ("13",),
    "Social": ("03",),
    "Security": ("13",),
    "Electrical and Electronics": ("29", "31"),
    "Machinery and Equipment": ("25",),
    "Textiles and Apparel": ("59", "61"),
    "Oil and Gas": ("75",),
    "Telecommunications": ("33",),
}


def _clean_text(value: object) -> str:
    text = BeautifulSoup(str(value or ""), "html.parser").get_text(" ")

    # The portal currently contains strings where UTF-8 bytes were decoded as
    # MacRoman (for example, ``‚Äô`` instead of a curly apostrophe). Repair
    # only non-ASCII runs that form valid UTF-8 after round-tripping; genuine
    # Unicode text that does not match that pattern is left untouched.
    def repair(match: re.Match[str]) -> str:
        try:
            return match.group(0).encode("mac_roman").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return match.group(0)

    # A few records were double-transcoded, so allow a second conservative
    # repair pass (for example ``‚âà√á`` -> ``≈Ç`` -> ``ł``).
    for _ in range(2):
        repaired = NON_ASCII_RUN.sub(repair, text)
        if repaired == text:
            break
        text = repaired
    return " ".join(text.replace("\xa0", " ").replace("\\", " ").split())


def _categories(value: object) -> list[str]:
    if isinstance(value, list):
        candidates = value
    else:
        candidates = str(value or "").split(",")
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


def _stable_id(title: str, company: str) -> str:
    identity = f"{title.casefold()}\n{company.casefold()}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"malaysia_rd_{digest}"


def _keywords(title: str, categories: list[str], programme: str) -> list[str]:
    stop = {
        "and", "the", "for", "from", "with", "using", "based", "product",
        "technology", "solution", "system",
    }
    words = re.findall(r"[a-z0-9]+", title.lower())
    title_terms = [word for word in words if len(word) > 2 and word not in stop]
    return list(dict.fromkeys([programme, *categories, *title_terms]))[:16]


def parse_products(payload: object) -> tuple[list[dict], int, int]:
    if isinstance(payload, list):
        indexed = list(enumerate(payload))
    elif isinstance(payload, dict):
        indexed = list(payload.items())
    else:
        raise ValueError("portal product collection is neither a list nor an object")

    records_by_identity: dict[tuple[str, str], dict] = {}
    invalid = 0
    for source_key, raw in indexed:
        if not isinstance(raw, dict):
            invalid += 1
            continue

        title = _clean_text(raw.get("Product Name") or raw.get("product_name") or raw.get("name"))
        summary = _clean_text(
            raw.get("Product Description")
            or raw.get("product_description")
            or raw.get("description")
        )
        company = _clean_text(raw.get("Company Name") or raw.get("company_name") or raw.get("company"))
        programme = _clean_text(raw.get("Programme") or raw.get("program"))
        categories = _categories(raw.get("Category") or raw.get("category"))
        if not title or not summary or not company:
            invalid += 1
            continue

        identity = (title.casefold(), company.casefold())
        detail_url = f"{PORTAL_URL}/{quote(str(source_key), safe='')}"
        if urlparse(detail_url).scheme != "https":
            invalid += 1
            continue

        sector_codes = _sector_codes(categories)
        record = {
            "id": _stable_id(title, company),
            "title": title,
            "summary": summary,
            "institute": company,
            "trl": "",
            "sector": ", ".join(categories) or "Other / Unclassified",
            "sector_codes": sector_codes,
            "classification_method": (
                "mosti_portal_category_mapping"
                if sector_codes
                else "portal_content_fallback"
            ),
            "classification_confidence": "high" if sector_codes else "low",
            "programme": programme,
            "keywords": _keywords(title, categories, programme),
            "url": detail_url,
        }

        # The current portal contains a small number of duplicate title/company
        # pairs. Keep the richer description while retaining one result only.
        existing = records_by_identity.get(identity)
        if existing is None or len(record["summary"]) > len(existing["summary"]):
            records_by_identity[identity] = record

    records = sorted(
        records_by_identity.values(),
        key=lambda record: (record["title"].casefold(), record["institute"].casefold()),
    )
    return records, len(indexed), invalid


async def fetch_products() -> object:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(DATA_URL, headers=HEADERS, timeout=60)
        response.raise_for_status()
        return response.json()


async def run(output: Path, minimum: int, replace_production: bool) -> list[dict]:
    resolved = resolve_output(output, PRODUCTION_PATH, replace_production)
    payload = await fetch_products()
    records, discovered, invalid = parse_products(payload)
    errors = validate_snapshot(
        records,
        minimum_records=minimum,
        discovered_count=discovered,
        failed_count=invalid,
        production_path=PRODUCTION_PATH,
        max_failure_rate=0.02,
    )
    if errors:
        raise ValueError("Malaysia portal crawl failed validation: " + "; ".join(errors))

    print_snapshot_diff(records, PRODUCTION_PATH)
    write_json_atomic(records, resolved)
    print(
        f"Saved {len(records)} unique records from {discovered} portal entries "
        f"to {resolved}; invalid={invalid}; duplicates={discovered - invalid - len(records)}"
    )
    for programme, count in sorted(
        Counter(
            next((keyword for keyword in record["keywords"] if keyword in {"MCY", "MySTI"}), "Other")
            for record in records
        ).items()
    ):
        print(f"  {programme}: {count}")
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=STAGING_PATH)
    parser.add_argument("--minimum", type=int, default=MINIMUM_RECORDS)
    parser.add_argument("--replace-production", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    asyncio.run(run(args.output, args.minimum, args.replace_production))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
