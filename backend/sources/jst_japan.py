from backend.sources.static_json_source import StaticJSONSource


JST_PATENT_LIST_URL = "https://www.jst.go.jp/chizai/en/patent_en.html"
JST_PATENT_PDF_BASE = "https://www.jst.go.jp/chizai/pdf"


class JSTJapanSource(StaticJSONSource):
    id = "jst_japan"
    name = "JST Japan Patent Portfolio"
    country = "Japan"
    institution = "Japan Science and Technology Agency (JST)"
    url = JST_PATENT_LIST_URL
    ttl_seconds = 86400
    transfer_type = "Patent licensing"
    last_indexed = "2026-06-30"
    org_default = "JST"
    encoding = "utf-8"

    def _to_technology(self, rec: dict):
        technology = super()._to_technology(rec)
        reference_id = str(rec.get("patent_no", "")).strip()
        has_granted_patent = reference_id.isdigit()
        official_url = (
            f"{JST_PATENT_PDF_BASE}/US{reference_id}B2.pdf"
            if has_granted_patent
            else JST_PATENT_LIST_URL
        )
        return technology.model_copy(
            update={
                "url": official_url,
                "reference_id": reference_id,
                "record_type": (
                    "US Patent" if has_granted_patent else "US Patent Application"
                ),
            }
        )
