import unittest
from unittest.mock import patch

from backend.sources.ip_australia import IPAustraliaSource


SAMPLE_RESULT = {
    "identifier": "2026214046",
    "auApplicationNumber": "2026214046",
    "inventionTitle": "Solar cell and preparation method",
    "patentType": "STANDARD",
    "filingDate": "2026-08-06",
    "earliestPriorityDate": "2025-08-19",
    "applicationStatus": "FILED",
    "applicants": "Example Solar Pty Ltd; Previous Applicant Ltd",
}


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"count": 41, "results": [SAMPLE_RESULT]}


class FakeClient:
    def __init__(self):
        self.url = ""
        self.params = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url, params):
        self.url = url
        self.params = params
        return FakeResponse()


class IPAustraliaSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_uses_public_api_and_page_offset(self):
        source = IPAustraliaSource()
        client = FakeClient()

        with patch("backend.sources.ip_australia.httpx.AsyncClient", return_value=client):
            results, total = await source.search("solar", {"page": 3})

        self.assertEqual(total, 41)
        self.assertEqual(len(results), 1)
        self.assertEqual(client.url, source._SEARCH_URL)
        self.assertEqual(client.params["query"], "solar")
        self.assertEqual(client.params["offset"], 40)
        self.assertEqual(client.params["limit"], 20)
        self.assertEqual(client.params["searchAbstractText"], "true")

    async def test_empty_query_does_not_call_api(self):
        source = IPAustraliaSource()
        with patch("backend.sources.ip_australia.httpx.AsyncClient") as client_class:
            results, total = await source.search("", {"page": 1})

        self.assertEqual((results, total), ([], 0))
        client_class.assert_not_called()

    def test_normalize_preserves_only_official_patent_metadata(self):
        item = IPAustraliaSource()._normalize(SAMPLE_RESULT)

        self.assertEqual(item.title, "Solar cell and preparation method")
        self.assertEqual(item.org_name, "Example Solar Pty Ltd")
        self.assertEqual(item.reference_id, "2026214046")
        self.assertEqual(item.patent_type, "STANDARD")
        self.assertEqual(item.reg_date, "2026-08-06")
        self.assertEqual(item.priority_date, "2025-08-19")
        self.assertEqual(item.dev_status, "FILED")
        self.assertEqual(item.record_type, "Patent record")
        self.assertEqual(item.summary, "")
        self.assertEqual(item.transfer_type, "")
        self.assertEqual(item.sector_codes, [])
        self.assertEqual(item.sector_labels, [])
        self.assertEqual(item.classification_method, "unclassified")


if __name__ == "__main__":
    unittest.main()
