import unittest

from backend.sources.jst_japan import JSTJapanSource, JST_PATENT_LIST_URL


class JSTJapanSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_granted_patent_uses_official_jst_pdf(self):
        source = JSTJapanSource()
        results, total = await source.search("TOBACCO BY2", {"page": 1})

        self.assertGreater(total, 0)
        item = results[0]
        self.assertEqual(item.reference_id, "8507220")
        self.assertEqual(item.record_type, "US Patent")
        self.assertEqual(
            item.url,
            "https://www.jst.go.jp/chizai/pdf/US8507220B2.pdf",
        )

    async def test_pending_application_uses_official_jst_listing(self):
        source = JSTJapanSource()
        results, total = await source.search("GENETIC MODIFICATION NON-HUMAN", {"page": 1})

        self.assertGreater(total, 0)
        item = results[0]
        self.assertEqual(item.reference_id, "17/661097")
        self.assertEqual(item.record_type, "US Patent Application")
        self.assertEqual(item.url, JST_PATENT_LIST_URL)


if __name__ == "__main__":
    unittest.main()
