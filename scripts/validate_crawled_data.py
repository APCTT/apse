"""Validate the bundled crawler outputs without making network requests.

Run after any crawler and before committing the resulting JSON:
    python scripts/validate_crawled_data.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


DATA_DIR = Path(__file__).parent.parent / "backend" / "sources" / "data"
REQUIRED_FIELDS = ("id", "title", "url")
NON_PRODUCTION_SUFFIXES = (".staging.json", ".checkpoint.json")


def _valid_http_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_file(path: Path) -> tuple[list[str], list[str], int]:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        records = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return [f"cannot parse JSON: {exc}"], [], 0

    if not isinstance(records, list):
        return ["top-level JSON value must be a list"], [], 0

    ids: list[str] = []
    normalized_titles: list[str] = []
    for index, record in enumerate(records):
        label = f"record {index + 1}"
        if not isinstance(record, dict):
            errors.append(f"{label}: must be an object")
            continue

        for field in REQUIRED_FIELDS:
            if not isinstance(record.get(field), str) or not record[field].strip():
                errors.append(f"{label}: missing non-empty {field!r}")

        record_id = record.get("id")
        if isinstance(record_id, str) and record_id:
            ids.append(record_id)

        title = record.get("title")
        if isinstance(title, str) and title.strip():
            normalized_titles.append(" ".join(title.lower().split()))

        if record.get("url") and not _valid_http_url(record["url"]):
            errors.append(f"{label}: invalid HTTP(S) URL")

    duplicate_ids = sorted(key for key, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        preview = ", ".join(duplicate_ids[:5])
        errors.append(f"{len(duplicate_ids)} duplicate IDs ({preview})")

    duplicate_titles = sum(
        count - 1 for count in Counter(normalized_titles).values() if count > 1
    )
    if duplicate_titles:
        warnings.append(f"{duplicate_titles} duplicate titles require review")

    if not records:
        errors.append("contains no records")

    return errors, warnings, len(records)


def main() -> int:
    paths = sorted(
        path
        for path in DATA_DIR.glob("*.json")
        if not path.name.endswith(NON_PRODUCTION_SUFFIXES)
    )
    if not paths:
        print(f"No crawler outputs found in {DATA_DIR}")
        return 1

    total_records = 0
    total_errors = 0
    for path in paths:
        errors, warnings, count = validate_file(path)
        total_records += count
        status = "FAIL" if errors else "OK"
        print(f"{status:4} {path.name:24} {count:5} records")
        for warning in warnings:
            print(f"     warning: {warning}")
        for error in errors:
            print(f"     error: {error}")
        total_errors += len(errors)

    print(
        f"\nChecked {len(paths)} files and {total_records} records; "
        f"{total_errors} validation errors."
    )
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
