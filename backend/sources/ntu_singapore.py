from backend.sources.static_json_source import StaticJSONSource


class NTUSingaporeSource(StaticJSONSource):
    id = "ntu_singapore"
    name = "NTU Singapore Tech Offers"
    country = "Singapore"
    institution = "Nanyang Technological University (NTU Singapore)"
    url = "https://www.ntu.edu.sg/innovates/tech-portal/tech-offers"
    ttl_seconds = 86400
    transfer_type = "Technology licensing / collaboration"
    last_indexed = "2026-10-08"
    org_default = "Nanyang Technological University (NTU Singapore)"
