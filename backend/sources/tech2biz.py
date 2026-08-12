from backend.sources.static_json_source import StaticJSONSource


class Tech2BizSource(StaticJSONSource):
    id = "tech2biz"
    name = "Tech2Biz Thailand"
    country = "Thailand"
    institution = "National Science and Technology Development Agency (NSTDA)"
    url = "https://www.tech2biz.net/content/inventor"
    ttl_seconds = 86400
    transfer_type = "Technology transfer / licensing"
    last_indexed = "2026-08-10"
    language = "th"
    org_default = "NSTDA"
    sector_provenance = "legacy_keyword"
