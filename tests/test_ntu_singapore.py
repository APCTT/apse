import unittest

from backend.sources.ntu_singapore import NTUSingaporeSource


class NTUSingaporeSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_snapshot_is_searchable(self):
        source = NTUSingaporeSource()
        results, total = await source.search("wireless communications", {"page": 1})

        self.assertGreater(total, 0)
        self.assertTrue(results)
        self.assertTrue(all(item.source_id == "ntu_singapore" for item in results))
        self.assertTrue(all(item.country == "Singapore" for item in results))
        self.assertTrue(all(item.url.startswith(source.url + "/detail/") for item in results))

    async def test_iso_sector_filter_uses_ntu_categories(self):
        source = NTUSingaporeSource()
        results, total = await source.search("", {"page": 1, "sector": "27"})

        self.assertGreater(total, 0)
        self.assertTrue(results)
        self.assertTrue(all("27" in item.sector_codes for item in results))


if __name__ == "__main__":
    unittest.main()
