from backend.sources.base import BaseSource
from backend.models.technology import Technology


class WIPOPatentscopeSource(BaseSource):
    id = "wipo_patentscope"
    name = "WIPO PATENTSCOPE"
    country = "International"
    institution = "World Intellectual Property Organization (WIPO)"
    status = "Search redirect"
    url = "https://patentscope.wipo.int/search/en/search.jsf"
    ttl_seconds = 86400
    access_method = "External search"

    async def search(self, query: str, filters: dict) -> tuple[list[Technology], int]:
        return [], 0

    def is_healthy(self) -> bool:
        return True
