"""ISO ICS-based technology sector normalization.

The source catalogues use unrelated category systems.  This module preserves
each source's original value and maps it to a small, relevant subset of the
International Classification for Standards (ICS).  It does not claim ISO
certification; it uses ISO ICS codes as the shared vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass


TAXONOMY_SCHEME = "ISO ICS"
TAXONOMY_VERSION = "7"


ICS_TOP_LEVEL_LABELS = {
    "01": "Generalities. Terminology. Standardization. Documentation",
    "03": "Services. Company organization, management and quality. Administration. Transport. Sociology",
    "07": "Natural and applied sciences",
    "11": "Health care technology",
    "13": "Environment. Health protection. Safety",
    "17": "Metrology and measurement. Physical phenomena",
    "19": "Testing",
    "21": "Mechanical systems and components for general use",
    "23": "Fluid systems and components for general use",
    "25": "Manufacturing engineering",
    "27": "Energy and heat transfer engineering",
    "29": "Electrical engineering",
    "31": "Electronics",
    "33": "Telecommunications. Audio and video engineering",
    "35": "Information technology",
    "37": "Image technology",
    "39": "Precision mechanics. Jewellery",
    "43": "Road vehicles engineering",
    "45": "Railway engineering",
    "47": "Shipbuilding and marine structures",
    "49": "Aircraft and space vehicle engineering",
    "53": "Materials handling equipment",
    "55": "Packaging and distribution of goods",
    "59": "Textile and leather technology",
    "61": "Clothing industry",
    "65": "Agriculture",
    "67": "Food technology",
    "71": "Chemical technology",
    "73": "Mining and minerals",
    "75": "Petroleum and related technologies",
    "77": "Metallurgy",
    "79": "Wood technology",
    "81": "Glass and ceramics industries",
    "83": "Rubber and plastic industries",
    "85": "Paper technology",
    "87": "Paint and colour industries",
    "91": "Construction materials and building",
    "93": "Civil engineering",
    "95": "Military affairs. Military engineering. Weapons",
    "97": "Domestic and commercial equipment. Entertainment. Sports",
}

# Detailed codes remain available for record-level classification. Facets roll
# them up to their two-digit parent so the public filter stays at the agreed
# 40-field ISO ICS level.
ICS_DETAIL_LABELS = {
    "07.080": "Biotechnology",
}

ICS_LABELS = {**ICS_TOP_LEVEL_LABELS, **ICS_DETAIL_LABELS}

OTHER_SECTOR_CODE = "other"
OTHER_SECTOR_LABEL = "Other / Unclassified"


SOURCE_SECTOR_MAP = {
    "agriculture": ("65",),
    "agriculture/biotechnology": ("65", "07.080"),
    "agro & food processing": ("65", "67"),
    "biotech": ("07.080",),
    "chemical": ("71",),
    "chemical and allied": ("71",),
    "civil engineering": ("93",),
    "coir": ("59",),
    "defence": ("95",),
    "electrical & electronics": ("29", "31"),
    "electronics": ("31",),
    "energy": ("27",),
    "energy/environment": ("27", "13"),
    "engineering sciences": ("25",),
    "environment": ("13",),
    "food": ("67",),
    "food & millet": ("67",),
    "glass & ceramics": ("81",),
    "health": ("11",),
    "health/medicine": ("11",),
    "herbal / home/ personal / hygiene care": ("71", "11"),
    "ict": ("35",),
    "it/software": ("35",),
    "life sciences": ("07.080",),
    "manufacturing": ("25",),
    "sericulture": ("65", "59"),
    # Korea National Technology Bank (NTB) official top-level categories.
    # Keep these source-native Korean labels here so live results can use the
    # same ISO ICS filters as locally indexed catalogues.
    "건설/교통": ("43", "45", "47", "49", "91", "93"),
    "건설·교통": ("43", "45", "47", "49", "91", "93"),
    "기계": ("25",),
    "기계ㆍ소재": ("25", "77", "81", "83"),
    "농림수산식품": ("65", "67"),
    "바이오ㆍ의료": ("07.080", "11"),
    "보건의료": ("11",),
    "생명·보건": ("07.080", "11"),
    "생명과학": ("07.080",),
    "섬유·화학": ("59", "71"),
    "세라믹": ("81",),
    "에너지/자원": ("27",),
    "에너지·자원": ("27",),
    "에너지ㆍ자원": ("27",),
    "원자력": ("27",),
    "재료": ("77", "81", "83"),
    "전기/전자": ("29", "31"),
    "전기ㆍ전자": ("29", "31"),
    "전기전자": ("29", "31"),
    "정보/통신": ("35",),
    "정보통신": ("35",),
    "지식서비스": ("35",),
    "화공": ("71",),
    "화학": ("71",),
    "환경": ("13",),
}

# APCTT's Drupal taxonomy uses the official top-level ISO ICS labels. Accept
# both those labels and their codes as exact, high-confidence source mappings.
SOURCE_SECTOR_MAP.update(
    {
        key: (code,)
        for code, label in ICS_TOP_LEVEL_LABELS.items()
        for key in (code.lower(), label.lower())
    }
)


# Fallbacks are intentionally conservative.  They are used only when a source
# gives a generic category such as "Technology" or "Materials".
KEYWORD_RULES = (
    ("07.080", ("biotech", "genome", "genetic", "cell culture", "enzyme", "microorganism")),
    ("11", ("medical", "health", "diagnos", "therap", "hospital", "pharma", "drug", "vaccine")),
    ("13", ("environment", "pollution", "wastewater", "waste water", "recycl", "emission", "sanitation")),
    ("27", ("solar", "renewable", "biofuel", "biomass", "battery", "energy", "heat pump", "hydrogen")),
    ("29", ("electrical", "electric power", "transformer", "inverter", "power grid")),
    ("31", ("semiconductor", "electronic", "circuit", "sensor", "photonic")),
    ("35", ("software", "artificial intelligence", "machine learning", "digital", "database", "iot", "cyber")),
    ("43", ("automotive", "road vehicle", "electric vehicle")),
    ("45", ("railway", "rail transport")),
    ("47", ("shipbuilding", "marine structure", "vessel")),
    ("49", ("aircraft", "aerospace", "space vehicle", "satellite")),
    ("65", ("agriculture", "agricultural", "crop", "farm", "fertiliz", "irrigation", "aquaculture", "fishery", "fisher")),
    ("67", ("food", "beverage", "nutrition", "postharvest", "ferment")),
    ("71", ("chemical", "catalyst", "solvent", "coating", "cosmetic", "essential oil")),
    ("77", ("metallurgy", "metal", "alloy", "steel", "aluminium", "aluminum")),
    ("81", ("ceramic", "glass")),
    ("83", ("polymer", "plastic", "rubber", "elastomer")),
    ("59", ("textile", "fabric", "fibre", "fiber", "coir", "sericulture")),
    ("91", ("building material", "construction material", "cement", "concrete")),
    ("93", ("civil engineering", "bridge", "road construction")),
    ("95", ("defence", "defense", "weapon", "military")),
    ("25", ("manufactur", "machin", "industrial process", "robot", "automation", "equipment")),
)


@dataclass(frozen=True)
class SectorClassification:
    source_sector: str
    codes: tuple[str, ...]
    labels: tuple[str, ...]
    method: str
    confidence: str

    @property
    def primary_label(self) -> str:
        return self.labels[0] if self.labels else OTHER_SECTOR_LABEL


def classify_sector(
    source_sector: str,
    *,
    title: str = "",
    summary: str = "",
    keywords: list[str] | None = None,
) -> SectorClassification:
    raw = (source_sector or "").strip()
    normalized = " ".join(raw.lower().split())
    direct_codes = SOURCE_SECTOR_MAP.get(normalized)
    if direct_codes:
        return _result(raw, direct_codes, "source_mapping", "high")

    text = " ".join([title, summary, " ".join(keywords or [])]).lower()
    codes = []
    for code, terms in KEYWORD_RULES:
        if any(term in text for term in terms):
            codes.append(code)

    # Avoid turning a single broad description into an unhelpful wall of
    # sectors while still allowing genuinely cross-sector technologies.
    unique_codes = tuple(dict.fromkeys(codes[:3]))
    if unique_codes:
        confidence = "medium" if normalized == "materials" else "low"
        method = "keyword_mapping" if normalized == "materials" else "keyword_fallback"
        return _result(raw, unique_codes, method, confidence)

    return SectorClassification(
        source_sector=raw,
        codes=(),
        labels=(),
        method="unclassified",
        confidence="low",
    )


def _result(
    raw: str,
    codes: tuple[str, ...],
    method: str,
    confidence: str,
) -> SectorClassification:
    valid_codes = tuple(code for code in codes if code in ICS_LABELS)
    return SectorClassification(
        source_sector=raw,
        codes=valid_codes,
        labels=tuple(ICS_LABELS[code] for code in valid_codes),
        method=method,
        confidence=confidence,
    )


def matches_sector_filter(classification: SectorClassification, filters: list[str]) -> bool:
    if not filters:
        return True
    if OTHER_SECTOR_CODE in filters and not classification.codes:
        return True
    return any(
        record_code == selected or record_code.startswith(f"{selected}.")
        for selected in filters
        for record_code in classification.codes
    )


def top_level_sector_codes(classification: SectorClassification) -> tuple[str, ...]:
    """Return unique two-digit ISO ICS parents for facet aggregation."""

    parents = (
        code.split(".", 1)[0]
        for code in classification.codes
    )
    return tuple(dict.fromkeys(
        code for code in parents if code in ICS_TOP_LEVEL_LABELS
    ))
