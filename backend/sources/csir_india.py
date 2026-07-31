from backend.sources.static_json_source import StaticJSONSource


class CSIRIndiaSource(StaticJSONSource):
    id = "csir_india"
    name = "CSIR India Technology Portal"
    country = "India"
    institution = "Council of Scientific and Industrial Research (CSIR)"
    url = "https://techindiacsir.anusandhan.net/online/Control.do?_tech="
    ttl_seconds = 86400
    transfer_type = "Technology transfer / licensing"
    sector_provenance = "legacy_keyword"
