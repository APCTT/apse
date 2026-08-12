from backend.sources.static_json_source import StaticJSONSource


class MalaysiaRDPortalSource(StaticJSONSource):
    id = "malaysia_rd_portal"
    name = "Malaysia R&D Commercialisation Portal"
    country = "Malaysia"
    institution = "MOSTI / MRANTI"
    url = "https://commercialisation.mosti.gov.my/rd-products"
    ttl_seconds = 86400
    transfer_type = "R&D product commercialisation / collaboration"
    last_indexed = "2026-08-12"
    org_default = "Malaysia R&D Commercialisation Portal"
