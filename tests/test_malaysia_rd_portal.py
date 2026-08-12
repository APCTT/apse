import unittest

from backend.sources.malaysia_rd_portal import MalaysiaRDPortalSource


class MalaysiaRDPortalSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_snapshot_is_searchable_and_uses_original_detail_url(self):
        source = MalaysiaRDPortalSource()
        results, total = await source.search("Agrivoltaic Mushroom Tunnel", {"page": 1})

        self.assertGreater(total, 0)
        item = next(result for result in results if result.title == "Agrivoltaic Mushroom Tunnel")
        self.assertEqual(item.country, "Malaysia")
        self.assertTrue(item.url.startswith("https://commercialisation.mosti.gov.my/rd-products/"))
        self.assertIn("65", item.sector_codes)
        self.assertIn("27", item.sector_codes)

    async def test_iso_sector_filter_uses_portal_category_mapping(self):
        source = MalaysiaRDPortalSource()
        results, total = await source.search(
            "Agrivoltaic Mushroom Tunnel",
            {"page": 1, "sector": "65"},
        )

        self.assertGreater(total, 0)
        self.assertTrue(all("65" in item.sector_codes for item in results))

    def test_snapshot_has_no_copied_contact_fields(self):
        source = MalaysiaRDPortalSource()
        source._load()

        forbidden = {"Business Email", "Business Address", "Cover Image"}
        self.assertTrue(source._records)
        self.assertTrue(all(forbidden.isdisjoint(record) for record in source._records))


if __name__ == "__main__":
    unittest.main()
