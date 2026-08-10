import asyncio
import unittest

from backend.sources.iti_sri_lanka import ITISriLankaSource


class ITISriLankaSourceTests(unittest.TestCase):
    def setUp(self):
        self.source = ITISriLankaSource()

    def test_local_index_is_available_and_countable(self):
        self.assertTrue(self.source.is_healthy())
        facets = self.source.sector_facets()
        self.assertEqual(102, sum(facets.values()))
        self.assertEqual(67, facets["67"])
        self.assertEqual(12, facets["13"])

    def test_keyword_search_returns_original_iti_document(self):
        results, total = asyncio.run(
            self.source.search("wastewater", {"page": 1})
        )
        self.assertGreaterEqual(total, 2)
        self.assertTrue(results)
        self.assertTrue(all(result.source_id == "iti_sri_lanka" for result in results))
        self.assertTrue(all(result.country == "Sri Lanka" for result in results))
        self.assertTrue(all(result.url.lower().endswith(".pdf") for result in results))

    def test_environment_filter_is_applied_to_the_complete_index(self):
        results, total = asyncio.run(
            self.source.search("", {"page": 1, "sector": "13"})
        )
        self.assertEqual(12, total)
        self.assertTrue(results)
        self.assertTrue(all("13" in result.sector_codes for result in results))


if __name__ == "__main__":
    unittest.main()
