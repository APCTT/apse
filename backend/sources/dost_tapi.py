from backend.sources.static_json_source import StaticJSONSource


class DOSTTAPISource(StaticJSONSource):
    id = "dost_tapi"
    name = "DOST-TAPI Philippines"
    country = "Philippines"
    institution = "Department of Science and Technology — Technology Application and Promotion Institute"
    url = "https://tapitechtransfer.dost.gov.ph/technologies"
    ttl_seconds = 86400
    transfer_type = "Technology transfer / licensing"
    org_default = "DOST-TAPI"
