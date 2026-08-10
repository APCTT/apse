"""Shared safeguards for manually refreshed crawler indexes."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


def resolve_output(
    output: Path,
    production_path: Path,
    replace_production: bool,
) -> Path:
    resolved = output.resolve()
    if resolved == production_path.resolve() and not replace_production:
        raise ValueError("production replacement requires --replace-production")
    return resolved


def _load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    return value if isinstance(value, list) else []


def validate_snapshot(
    records: list[dict],
    *,
    minimum_records: int,
    discovered_count: int,
    failed_count: int,
    production_path: Path,
    max_failure_rate: float = 0.05,
    max_drop_fraction: float = 0.15,
) -> list[str]:
    """Reject incomplete snapshots before any output file is written."""
    errors: list[str] = []
    count = len(records)
    if count < minimum_records:
        errors.append(
            f"record count {count} is below safety minimum {minimum_records}"
        )
    if discovered_count <= 0:
        errors.append("crawler discovered no detail URLs")
    elif failed_count / discovered_count > max_failure_rate:
        errors.append(
            f"detail failure rate {failed_count}/{discovered_count} exceeds "
            f"{max_failure_rate:.0%}"
        )

    ids: list[str] = []
    urls: list[str] = []
    for index, record in enumerate(records, start=1):
        for field in ("id", "title", "url"):
            if not str(record.get(field, "")).strip():
                errors.append(f"record {index} has no {field}")
        record_id = str(record.get("id", "")).strip()
        url = str(record.get("url", "")).strip()
        if record_id:
            ids.append(record_id)
        if url:
            urls.append(url)
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append(f"record {index} has an invalid URL")

    if len(ids) != len(set(ids)):
        errors.append("duplicate record IDs found")
    if len(urls) != len(set(urls)):
        errors.append("duplicate record URLs found")

    previous = _load_records(production_path)
    if previous:
        minimum_from_previous = int(len(previous) * (1 - max_drop_fraction))
        if count < minimum_from_previous:
            errors.append(
                f"record count dropped from {len(previous)} to {count}, beyond the "
                f"allowed {max_drop_fraction:.0%}"
            )
    return errors


def snapshot_diff(records: list[dict], production_path: Path) -> dict[str, int]:
    previous = _load_records(production_path)
    old = {str(record.get("id")): record for record in previous}
    new = {str(record.get("id")): record for record in records}
    shared = old.keys() & new.keys()
    return {
        "previous": len(old),
        "current": len(new),
        "added": len(new.keys() - old.keys()),
        "removed": len(old.keys() - new.keys()),
        "changed": sum(old[key] != new[key] for key in shared),
    }


def write_json_atomic(records: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)


def print_snapshot_diff(records: list[dict], production_path: Path) -> None:
    diff = snapshot_diff(records, production_path)
    print(
        "Snapshot diff: "
        f"previous={diff['previous']}, current={diff['current']}, "
        f"added={diff['added']}, removed={diff['removed']}, "
        f"changed={diff['changed']}"
    )
