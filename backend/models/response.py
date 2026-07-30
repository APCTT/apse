from pydantic import BaseModel, Field
from backend.models.technology import Technology


class SearchResponse(BaseModel):
    query: str
    total: int
    sources_hit: int
    results: list[Technology]
    cached: bool
    source_totals: dict[str, int] = Field(default_factory=dict)
    partial: bool = False
    failed_sources: list[str] = Field(default_factory=list)
