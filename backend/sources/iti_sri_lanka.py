from backend.sources.static_json_source import StaticJSONSource


class ITISriLankaSource(StaticJSONSource):
    id = "iti_sri_lanka"
    name = "ITI Sri Lanka Technology Bank"
    country = "Sri Lanka"
    institution = "Industrial Technology Institute (ITI)"
    url = "https://www.iti.lk/technology-transfer/"
    ttl_seconds = 86400
    transfer_type = "Technology transfer / licensing"
    last_indexed = "2026-08-10"
    org_default = "Industrial Technology Institute (ITI)"
