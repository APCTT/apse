from abc import ABC, abstractmethod
from backend.models.technology import Technology, Source


class BaseSource(ABC):
    id: str
    name: str
    country: str
    institution: str
    status: str
    url: str
    ttl_seconds: int = 86400
    # Constant across all records for this source, used by the Transfer Type
    # filter. Left blank where it genuinely varies per record (e.g. Korea NTB)
    # or doesn't apply (e.g. WIPO's external redirect).
    transfer_type: str = ""
    # True only when the source can return complete, correctly paginated
    # results for an ISO ICS sector filter.
    sector_filter_supported: bool = False
    # True when this source has a local index that can be counted without
    # making an upstream API request.
    facet_count_supported: bool = False
    # Multi-country catalogues apply country filters to individual records.
    multi_country: bool = False
    # Live catalogues may hydrate a short-lived index before facet counting.
    requires_facet_preparation: bool = False

    @abstractmethod
    async def search(self, query: str, filters: dict) -> tuple[list[Technology], int]:
        ...

    @abstractmethod
    def is_healthy(self) -> bool:
        ...

    def to_source_model(self) -> Source:
        return Source(
            id=self.id,
            name=self.name,
            country=self.country,
            institution=self.institution,
            status=self.status,
            url=self.url,
            ttl_seconds=self.ttl_seconds,
            transfer_type=self.transfer_type,
            sector_filter_supported=self.sector_filter_supported,
            multi_country=self.multi_country,
        )

    async def prepare_facets(self) -> None:
        return None

    def sector_facets(self) -> dict[str, int]:
        return {}

    def facet_records(self):
        """Yield locally indexed records used for query-aware facet counts.

        Live API and redirect sources intentionally return no records here so
        computing filter counts never triggers upstream requests.
        """
        return ()
