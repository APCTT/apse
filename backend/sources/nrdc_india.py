from backend.sources.static_json_source import StaticJSONSource


class NRDCIndiaSource(StaticJSONSource):
    id = "nrdc_india"
    name = "NRDC India Technology Portal"
    country = "India"
    institution = "National Research Development Corporation (NRDC)"
    url = "https://nrdcindia.com/Pages/Technology Available for Commercialization"
    ttl_seconds = 86400
    transfer_type = "Technology transfer / licensing"
    last_indexed = "2026-08-10"
    org_default = "NRDC"
