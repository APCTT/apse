from datetime import datetime
from pydantic import BaseModel, Field


class Technology(BaseModel):
    id: str
    title: str
    summary: str
    sector: str
    language: str
    keywords: list[str]
    country: str
    source_id: str
    source_name: str
    url: str
    fetched_at: datetime
    # Optional source-specific detail fields
    org_name: str = ""
    transfer_type: str = ""
    dev_status: str = ""
    reg_date: str = ""
    sub_sector: str = ""
    # Generic record metadata used by catalogue types that are not technology
    # transfer offers (for example, patent search records).
    record_type: str = ""
    reference_id: str = ""
    patent_type: str = ""
    priority_date: str = ""
    # Shared taxonomy fields. `source_sector` preserves the provider's original
    # category while `sector_codes` and `sector_labels` use ISO ICS.
    source_sector: str = ""
    sector_codes: list[str] = Field(default_factory=list)
    sector_labels: list[str] = Field(default_factory=list)
    taxonomy_scheme: str = ""
    taxonomy_version: str = ""
    classification_method: str = ""
    classification_confidence: str = ""


class Source(BaseModel):
    id: str
    name: str
    country: str
    institution: str
    status: str
    url: str
    ttl_seconds: int
    transfer_type: str = ""
    sector_filter_supported: bool = False
    multi_country: bool = False
    access_method: str = ""
    last_indexed: str = ""
