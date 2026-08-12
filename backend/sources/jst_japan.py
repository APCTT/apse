from backend.sources.static_json_source import StaticJSONSource


class JSTJapanSource(StaticJSONSource):
    id = "jst_japan"
    name = "JST Japan Patent Portfolio"
    country = "Japan"
    institution = "Japan Science and Technology Agency (JST)"
    url = "https://www.jst.go.jp/chizai/en/patent_en.html"
    ttl_seconds = 86400
    transfer_type = "Patent licensing"
    last_indexed = "2026-06-30"
    org_default = "JST"
    encoding = "utf-8"
