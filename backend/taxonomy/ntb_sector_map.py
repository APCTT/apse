"""Verified Korea NTB category-code mapping to the Gateway's ISO ICS sectors.

The source table is kept as CSV so the mapping can be reviewed and updated
without reading Python code.  NTB category codes and names come from the
official KIAT technology-category dataset dated 2025-11-04.
"""

from __future__ import annotations

import csv
from pathlib import Path

from backend.taxonomy.iso_ics import (
    ICS_LABELS,
    SectorClassification,
    classify_sector,
)


MAPPING_PATH = Path(__file__).with_name("data") / "ntb_to_ics.csv"


def _split_codes(value: str) -> tuple[str, ...]:
    return tuple(code.strip() for code in value.split(";") if code.strip())


def _load_mapping() -> tuple[
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
    dict[str, str],
]:
    code_map: dict[str, tuple[str, ...]] = {}
    label_map: dict[str, tuple[str, ...]] = {}
    query_map: dict[str, str] = {}

    with MAPPING_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            ntb_code = row["ntb_code"].strip()
            ntb_label = row["ntb_label"].strip()
            ics_codes = _split_codes(row["ics_codes"])
            invalid = [code for code in ics_codes if code not in ICS_LABELS]
            if invalid:
                raise ValueError(f"Unknown ISO ICS code(s) in NTB mapping: {invalid}")

            code_map[ntb_code] = ics_codes
            if ntb_label:
                existing = label_map.get(ntb_label, ())
                label_map[ntb_label] = tuple(dict.fromkeys((*existing, *ics_codes)))

            for ics_code in _split_codes(row["preferred_query_for"]):
                if ics_code in query_map:
                    raise ValueError(f"Duplicate preferred NTB query mapping for {ics_code}")
                query_map[ics_code] = ntb_code

    return code_map, label_map, query_map


NTB_CODE_TO_ICS, NTB_LABEL_TO_ICS, ICS_TO_NTB_QUERY_CODE = _load_mapping()


def classify_ntb_sector(
    *,
    primary_code: str = "",
    middle_code: str = "",
    primary_name: str = "",
    middle_name: str = "",
    title: str = "",
    summary: str = "",
    keywords: list[str] | None = None,
) -> SectorClassification:
    """Classify an NTB record, preferring its verified native code.

    The more specific middle code is checked before the broad primary code.
    Older/sample responses without codes fall back to an exact official label,
    then to the shared conservative keyword classifier.
    """

    source_sector = (primary_name or middle_name).strip()
    for code in (middle_code.strip(), primary_code.strip()):
        if code and code in NTB_CODE_TO_ICS:
            return _result(source_sector, NTB_CODE_TO_ICS[code], "ntb_code_mapping")

    for label in (middle_name.strip(), primary_name.strip()):
        if label and label in NTB_LABEL_TO_ICS:
            return _result(source_sector, NTB_LABEL_TO_ICS[label], "ntb_label_mapping")

    return classify_sector(
        source_sector,
        title=title,
        summary=summary,
        keywords=keywords,
    )


def ntb_query_codes_for_ics(selected_codes: list[str]) -> tuple[str, ...]:
    """Return the preferred NTB native codes for selected ISO ICS filters."""

    native_codes: list[str] = []
    for selected in selected_codes:
        for ics_code, ntb_code in ICS_TO_NTB_QUERY_CODE.items():
            if ics_code == selected or ics_code.startswith(f"{selected}."):
                native_codes.append(ntb_code)
    return tuple(dict.fromkeys(native_codes))


def _result(
    source_sector: str,
    codes: tuple[str, ...],
    method: str,
) -> SectorClassification:
    return SectorClassification(
        source_sector=source_sector,
        codes=codes,
        labels=tuple(ICS_LABELS[code] for code in codes),
        method=method,
        confidence="high",
    )
