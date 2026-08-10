"""
Crawler: Tech2Biz Thailand — technology transfer platform
https://www.tech2biz.net/content/inventor

The safe default writes a staging file and preserves the original Thai text.
MyMemory translation is optional because its anonymous quota is too small for
a complete catalogue refresh.

Run from the repository root:
    python scripts/crawl_tech2biz.py
    python scripts/crawl_tech2biz.py --translate-mymemory

Writing directly to the production index requires an explicit opt-in:
    python scripts/crawl_tech2biz.py \
        --output backend/sources/data/tech2biz.json \
        --replace-production

Requirements: httpx, beautifulsoup4
"""

import argparse
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import unquote, urljoin

import httpx
from bs4 import BeautifulSoup

BASE = "https://www.tech2biz.net"
LIST_URL = f"{BASE}/content/inventor"
REPO_ROOT = Path(__file__).parent.parent
PRODUCTION_PATH = REPO_ROOT / "backend" / "sources" / "data" / "tech2biz.json"
STAGING_PATH = REPO_ROOT / "backend" / "sources" / "data" / "tech2biz.staging.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; APCTT-Gateway-Crawler/1.0)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "th,en-US;q=0.8,en;q=0.7",
}
CONCURRENCY = 3
PAGE_DELAY = 0.6
TECH_DELAY = 0.4
TRANSLATE_DELAY = 0.5
MIN_EXPECTED_RECORDS = 500

TRANSLATION_ERROR_MARKERS = (
    "MYMEMORY WARNING",
    "YOU USED ALL AVAILABLE FREE TRANSLATIONS",
    "NEXT AVAILABLE IN",
    "QUERY LENGTH LIMIT EXCEEDED",
    "INVALID EMAIL",
)


def _contains_translation_error(text: str) -> bool:
    upper = (text or "").upper()
    return any(marker in upper for marker in TRANSLATION_ERROR_MARKERS)


def _translation_from_response(original: str, data: dict) -> tuple[str, str]:
    """Return safe text and status without ever exposing API error messages."""

    response_status = data.get("responseStatus")
    translated = str(data.get("responseData", {}).get("translatedText", "") or "").strip()
    response_details = str(data.get("responseDetails", "") or "")

    if response_status not in (None, 200, "200"):
        status = "quota_exceeded" if response_status in (429, "429") else "api_error"
        return original, status
    if _contains_translation_error(translated) or _contains_translation_error(response_details):
        return original, "quota_exceeded"
    if not translated or translated.casefold() == original.strip().casefold():
        return original, "original_preserved"
    return translated, "translated"


async def translate_th_en(client: httpx.AsyncClient, text: str) -> tuple[str, str]:
    """Translate Thai to English, preserving Thai on every failure."""

    original = (text or "").strip()
    if not original:
        return original, "empty"
    try:
        response = await client.get(
            "https://api.mymemory.translated.net/get",
            params={"q": original[:400], "langpair": "th|en"},
            timeout=10,
        )
        return _translation_from_response(original, response.json())
    except Exception:
        return original, "api_error"


async def get_tech_urls_page(client: httpx.AsyncClient, page: int) -> list[str]:
    url = f"{LIST_URL}?page={page}" if page > 0 else LIST_URL
    response = await client.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    urls = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if (
            re.match(r"^/content/\d+-", href)
            or re.match(r"^https?://www\.tech2biz\.net/content/\d+-", href)
        ):
            full = urljoin(BASE, href)
            if full not in urls:
                urls.append(full)
    return urls


def _detect_sector(text: str) -> str:
    mapping = [
        ("Agriculture", ["agri", "crop", "farm", "soil", "fertiliz", "seed", "plant", "rice",
                         "fish", "aqua", "food safety", "pesticide", "herb"]),
        ("Health", ["health", "medic", "pharma", "drug", "diagnos", "therapeut", "disease",
                    "pathogen", "antibacter", "antiviral", "wound", "hospital"]),
        ("Food", ["food", "nutrition", "beverage", "ferment", "postharvest", "cooking", "flour"]),
        ("Energy", ["energy", "solar", "battery", "fuel", "biomass", "biofuel", "power"]),
        ("Environment", ["water", "waste", "environ", "recycl", "pollution", "treatment"]),
        ("Materials", ["material", "composite", "coating", "polymer", "textile", "fabric",
                       "nano", "rubber", "adhesive", "paint"]),
        ("ICT", ["software", "app", "digital", "iot", "sensor", "data", "system", "platform"]),
        ("Manufacturing", ["manufactur", "machin", "equipment", "tool", "process", "industrial"]),
    ]
    low = text.lower()
    for sector, keywords in mapping:
        if any(keyword in low for keyword in keywords):
            return sector
    return "Technology"


def extract_id(url: str) -> str:
    match = re.search(r"/content/(\d+)-", url)
    return match.group(1) if match else url.split("/")[-1]


def _title_from_url(url: str, tech_id: str) -> str:
    slug = unquote(url.rstrip("/").split("/")[-1])
    prefix = f"{tech_id}-"
    title = slug[len(prefix):] if slug.startswith(prefix) else slug
    title = title.replace("-", " ").strip()
    return title or f"Technology {tech_id}"


def parse_tech_page(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    tech_id = extract_id(url)

    title_th = ""
    for selector in (
        "#page-content .line-bottom span.h2.font-weight-bold",
        "#page-content span.h2.font-weight-bold",
        "h1",
        "h2.title",
        ".content-title",
        "h2",
        ".card-title",
    ):
        element = soup.select_one(selector)
        text = element.get_text(" ", strip=True) if element else ""
        if len(text) > 2 and text.casefold() != "tech2biz":
            title_th = text
            break
    if not title_th:
        title_th = _title_from_url(url, tech_id)

    content_root = (
        soup.select_one("#page-content .content-detail.d-none.d-sm-block")
        or soup.select_one("#page-content .content-detail")
        or soup.select_one("#page-content")
    )
    paragraphs = []
    if content_root:
        for block in content_root.select(".d-block.font-normal-16px.mb-3"):
            text = block.get_text(" ", strip=True)
            if len(text) > 20 and text not in paragraphs:
                paragraphs.append(text)
    if not paragraphs and content_root:
        for paragraph in content_root.find_all("p"):
            text = paragraph.get_text(" ", strip=True)
            if len(text) > 20 and text not in paragraphs:
                paragraphs.append(text)
    summary_th = " ".join(paragraphs[:3])[:1200]

    trl = ""
    status_element = soup.select_one(".font-30px.text-center.text-success")
    status_text = status_element.get_text(" ", strip=True) if status_element else ""
    status_map = (
        ("ถ่ายทอด", "Transfer"),
        ("transfer", "Transfer"),
        ("ต้นแบบ", "Prototype"),
        ("prototype", "Prototype"),
        ("ทดลอง", "Experimental"),
        ("experimental", "Experimental"),
        ("เริ่มต้น", "Initial"),
        ("initial", "Initial"),
    )
    status_lower = status_text.lower()
    for marker, label in status_map:
        if marker in status_lower:
            trl = label
            break
    if not trl and "TRL" in status_text:
        match = re.search(r"TRL[-\s]*(\d)", status_text, re.IGNORECASE)
        if match:
            trl = f"TRL-{match.group(1)}"

    institute = "Tech2Biz Thailand"
    institute_element = soup.select_one(".conversation-panel .font-weight-bold")
    if institute_element:
        candidate = institute_element.get_text(" ", strip=True)
        if len(candidate) > 3:
            institute = candidate

    return {
        "tech_id": tech_id,
        "title_th": title_th,
        "summary_th": summary_th,
        "trl": trl,
        "institute": institute,
        "url": url,
    }


async def crawl_tech_page(
    client: httpx.AsyncClient,
    url: str,
    idx: int,
    total: int,
) -> dict | None:
    try:
        response = await client.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except Exception as exc:
        print(f"  [{idx}/{total}] FAILED {url} — {exc}")
        return None
    return parse_tech_page(response.text, url)


def validate_records(records: list[dict], minimum: int = MIN_EXPECTED_RECORDS) -> list[str]:
    errors = []
    if len(records) < minimum:
        errors.append(f"record count {len(records)} is below the minimum {minimum}")

    ids = [str(record.get("id", "")) for record in records]
    urls = [str(record.get("url", "")) for record in records]
    if len(ids) != len(set(ids)):
        errors.append("duplicate record IDs found")
    if len(urls) != len(set(urls)):
        errors.append("duplicate record URLs found")

    missing_title = sum(not str(record.get("title_original", "")).strip() for record in records)
    missing_summary = sum(not str(record.get("summary_original", "")).strip() for record in records)
    translation_errors = sum(
        _contains_translation_error(
            " ".join([
                str(record.get("title", "")),
                str(record.get("summary", "")),
            ])
        )
        for record in records
    )
    if missing_title:
        errors.append(f"{missing_title} records have no original title")
    if missing_summary:
        errors.append(f"{missing_summary} records have no original summary")
    if translation_errors:
        errors.append(f"{translation_errors} records contain translation error text")
    return errors


def write_records(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary_path.replace(output_path)


async def run(args: argparse.Namespace) -> None:
    output_path = args.output.resolve()
    if output_path == PRODUCTION_PATH.resolve() and not args.replace_production:
        raise SystemExit(
            "Refusing to overwrite the production index without --replace-production"
        )

    async with httpx.AsyncClient(follow_redirects=True) as client:
        print("=== Tech2Biz Thailand Safe Crawler ===")
        print("Step 1: Collecting technology URLs...")

        response = await client.get(LIST_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        last_page = 0
        for anchor in soup.find_all("a", href=True):
            match = re.search(r"[?&]page=(\d+)", anchor["href"])
            if match:
                last_page = max(last_page, int(match.group(1)))

        all_urls = []
        for page in range(0, last_page + 1):
            urls = await get_tech_urls_page(client, page)
            all_urls.extend(urls)
            print(
                f"  Page {page + 1}/{last_page + 1}: "
                f"+{len(urls)} URLs (total {len(all_urls)})"
            )
            await asyncio.sleep(PAGE_DELAY)

        all_urls = list(dict.fromkeys(all_urls))
        total = len(all_urls)
        print(f"\nStep 2: Crawling {total} technology pages...\n")

        raw_records = []
        for offset in range(0, total, CONCURRENCY):
            batch = all_urls[offset:offset + CONCURRENCY]
            tasks = [
                crawl_tech_page(client, url, offset + index + 1, total)
                for index, url in enumerate(batch)
            ]
            records = await asyncio.gather(*tasks)
            raw_records.extend(record for record in records if record)
            if len(raw_records) % 30 < CONCURRENCY:
                print(f"  Crawled {len(raw_records)}/{total}")
            await asyncio.sleep(TECH_DELAY)

        translation_enabled = bool(args.translate_mymemory)
        if translation_enabled:
            print(f"\nStep 3: Translating up to {len(raw_records)} records with MyMemory...\n")
        else:
            print("\nStep 3: Translation skipped; preserving original Thai text.\n")

        final = []
        for index, record in enumerate(raw_records):
            title = record["title_th"]
            summary = record["summary_th"]
            title_status = "not_requested"
            summary_status = "not_requested"

            if translation_enabled:
                title, title_status = await translate_th_en(client, record["title_th"])
                if title_status == "quota_exceeded":
                    translation_enabled = False
                    print(
                        "  MyMemory quota/error response detected. "
                        "Further translations disabled; Thai originals preserved."
                    )
                else:
                    summary, summary_status = await translate_th_en(
                        client,
                        record["summary_th"][:400],
                    )
                    if summary_status == "quota_exceeded":
                        translation_enabled = False
                        print(
                            "  MyMemory quota/error response detected. "
                            "Further translations disabled; Thai originals preserved."
                        )
                await asyncio.sleep(TRANSLATE_DELAY)

            classification_text = " ".join(
                value
                for value, status in (
                    (title, title_status),
                    (summary, summary_status),
                )
                if status == "translated"
            )
            sector = _detect_sector(classification_text) if classification_text else "Technology"
            keyword_source = title if title_status == "translated" else ""
            stop_words = {"that", "the", "and", "for", "with", "from", "into", "using", "based"}
            keywords = [
                word.lower()
                for word in re.split(r"\W+", keyword_source)
                if len(word) > 3 and word.lower() not in stop_words
            ]

            final.append({
                "id": f"tech2biz_{record['tech_id']}",
                "tech_id": record["tech_id"],
                "title": title,
                "summary": summary,
                "title_original": record["title_th"],
                "summary_original": record["summary_th"],
                "title_translation_status": title_status,
                "summary_translation_status": summary_status,
                "institute": record["institute"],
                "trl": record["trl"],
                "sector": sector,
                "keywords": keywords[:10],
                "url": record["url"],
            })

            if (index + 1) % 50 == 0:
                print(f"  Prepared {index + 1}/{len(raw_records)}")

    errors = validate_records(final, minimum=args.minimum_records)
    if errors:
        print("\nValidation failed; no output written:")
        for error in errors:
            print(f"  - {error}")
        raise SystemExit(1)

    write_records(final, output_path)
    print(f"\nDone. {len(final)}/{total} technologies saved to {output_path}")
    print("Validation passed: record count, unique IDs/URLs, originals, translation errors")
    for record in final[:5]:
        print(f"  • [{record['sector']}] {record['title'][:70]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely crawl the Tech2Biz catalogue")
    parser.add_argument(
        "--output",
        type=Path,
        default=STAGING_PATH,
        help=f"output JSON path (default: {STAGING_PATH})",
    )
    parser.add_argument(
        "--translate-mymemory",
        action="store_true",
        help="attempt MyMemory translation and preserve Thai on quota/error responses",
    )
    parser.add_argument(
        "--replace-production",
        action="store_true",
        help="required when --output points to the production tech2biz.json",
    )
    parser.add_argument(
        "--minimum-records",
        type=int,
        default=MIN_EXPECTED_RECORDS,
        help=f"refuse to write fewer than this many records (default: {MIN_EXPECTED_RECORDS})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
