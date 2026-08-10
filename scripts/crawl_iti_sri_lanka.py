"""Build the local index for ITI Sri Lanka's public technology list.

ITI's Technology Transfer page labels the linked catalogue "Available
Technologies", even though the destination currently has a legacy URL and
HTML title containing "commercialized-technologies".  The crawler verifies
that upstream link before accepting the catalogue and never visits ITI's
separate Commercialized Technologies page.

The default output is a staging file.  Replacing the production index requires
an explicit output path and ``--replace-production``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


BASE_URL = "https://www.iti.lk"
TRANSFER_URL = f"{BASE_URL}/technology-transfer/"
AVAILABLE_URL = f"{BASE_URL}/vacancies-template/commercialized-technologies/"
COMMERCIALIZED_URL = f"{BASE_URL}/commercialized-technologies/"

ROOT = Path(__file__).parent.parent
PRODUCTION_PATH = ROOT / "backend" / "sources" / "data" / "iti_sri_lanka.json"
STAGING_PATH = ROOT / "backend" / "sources" / "data" / "iti_sri_lanka.staging.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; APCTT-Gateway-Crawler/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}

ALLOWED_CATEGORIES = {"Food", "Herbal", "Environment"}
MINIMUM_RECORDS = 80
EXCLUDED_DOCUMENT_HOSTS = {
    # One legacy Food document still points to ITI's retired numeric host and
    # consistently times out. Keep broken originals out of the public index.
    "192.248.98.14",
}

HERBAL_FOOD_TERMS = (
    "beverage", "drink", "jam", "marmalade", "tea", "leaf powder",
)
HERBAL_HEALTH_TERMS = (
    "burn cream", "nutraceutical", "anti-lice", "mouthwash", "toothpaste",
    "tablet", "pain off", "quality detection kit",
)


def _clean_text(value: str) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def _normalized_url(value: str) -> str:
    return urljoin(f"{BASE_URL}/", value.strip())


def _stable_id(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"iti_sri_lanka_{digest}"


def _keywords(title: str) -> list[str]:
    stop = {
        "and", "the", "for", "from", "with", "using", "based", "ready",
        "serve", "technology", "technologies",
    }
    words = re.findall(r"[a-z0-9]+", title.lower())
    return list(dict.fromkeys(word for word in words if len(word) > 2 and word not in stop))[:10]


def sector_for(category: str, title: str) -> tuple[str, str]:
    """Return one conservative ISO ICS top-level code and confidence."""
    if category == "Food":
        return "67", "high"
    if category == "Environment":
        return "13", "high"
    if category == "Herbal":
        lowered = title.lower()
        if any(term in lowered for term in HERBAL_FOOD_TERMS):
            return "67", "medium"
        if any(term in lowered for term in HERBAL_HEALTH_TERMS):
            return "11", "medium"
        return "71", "medium"
    return "other", "low"


def verify_available_catalogue_link(transfer_html: str) -> None:
    """Verify that ITI itself still labels AVAILABLE_URL as available tech."""
    soup = BeautifulSoup(transfer_html, "html.parser")
    matching = []
    for link in soup.select("a[href]"):
        label = _clean_text(link.get_text("", strip=False)).lower()
        href = _normalized_url(link.get("href", ""))
        if label == "available technologies":
            matching.append(href)
    if AVAILABLE_URL not in matching:
        raise ValueError(
            "ITI no longer links the expected catalogue as 'Available Technologies'; "
            "manual status review is required"
        )


def parse_available_technologies(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("#defaultPage .wrap-default-page")
    if content is None:
        raise ValueError("ITI catalogue content container was not found")

    category = ""
    records: list[dict] = []
    seen_urls: set[str] = set()

    for node in content.find_all(["h2", "h3", "h4", "a"]):
        if node.name in {"h2", "h3", "h4"}:
            candidate = _clean_text(node.get_text("", strip=False))
            if candidate in ALLOWED_CATEGORIES:
                category = candidate
            continue

        href = node.get("href", "").strip()
        if not href or not urlparse(href).path.lower().endswith(".pdf"):
            continue
        if not category:
            raise ValueError("PDF link appeared before a recognized ITI category")

        url = _normalized_url(href)
        if (urlparse(url).hostname or "").lower() in EXCLUDED_DOCUMENT_HOSTS:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Preserve whitespace present in the original text nodes. ITI uses
        # adjacent inline tags in the middle of some words ("Instan" + "t")
        # and between others ("Processing " + "Technology").
        title = _clean_text(node.get_text("", strip=False))
        if not title:
            title = _clean_text(Path(urlparse(url).path).stem.replace("_", " "))
        sector_code, confidence = sector_for(category, title)

        records.append({
            "id": _stable_id(url),
            "tech_id": _stable_id(url).removeprefix("iti_sri_lanka_"),
            "title": title,
            "summary": (
                f"Technology listed by Sri Lanka's Industrial Technology Institute "
                f"under {category}. Open the original ITI document for details and "
                "confirm current transfer availability with the source institution."
            ),
            "institute": "Industrial Technology Institute (ITI)",
            "trl": "",
            "sector": category,
            "sector_code": sector_code,
            "classification_method": "iti_category_title_mapping",
            "classification_confidence": confidence,
            "keywords": _keywords(title),
            "url": url,
        })

    return records


def validate_records(records: list[dict], minimum: int = MINIMUM_RECORDS) -> list[str]:
    errors: list[str] = []
    if len(records) < minimum:
        errors.append(f"record count {len(records)} is below safety minimum {minimum}")

    ids = [record.get("id") for record in records]
    urls = [record.get("url") for record in records]
    if len(ids) != len(set(ids)):
        errors.append("duplicate record IDs found")
    if len(urls) != len(set(urls)):
        errors.append("duplicate record URLs found")

    for index, record in enumerate(records, start=1):
        if not record.get("title"):
            errors.append(f"record {index} has no title")
        if record.get("sector") not in ALLOWED_CATEGORIES:
            errors.append(f"record {index} has an unknown source category")
        parsed = urlparse(str(record.get("url", "")))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"record {index} has an invalid URL")
        if str(record.get("url", "")).rstrip("/") == COMMERCIALIZED_URL.rstrip("/"):
            errors.append(f"record {index} points to the excluded commercialized catalogue")
    return errors


async def fetch_html(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def resolve_output(path: Path, replace_production: bool) -> Path:
    resolved = path.resolve()
    if resolved == PRODUCTION_PATH.resolve() and not replace_production:
        raise ValueError("production replacement requires --replace-production")
    return resolved


async def run(output: Path, minimum: int, replace_production: bool) -> list[dict]:
    output = resolve_output(output, replace_production)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        transfer_html, catalogue_html = await asyncio.gather(
            fetch_html(client, TRANSFER_URL),
            fetch_html(client, AVAILABLE_URL),
        )

    verify_available_catalogue_link(transfer_html)
    records = parse_available_technologies(catalogue_html)
    errors = validate_records(records, minimum=minimum)
    if errors:
        raise ValueError("ITI crawl failed validation: " + "; ".join(errors))

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Saved {len(records)} ITI records to {output}")
    for category, count in sorted(Counter(record["sector"] for record in records).items()):
        print(f"  {category}: {count}")
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
