import unittest
import xml.etree.ElementTree as ET

from backend.sources.korea_ntb import KoreaNTBSource


class KoreaNTBSectorTests(unittest.TestCase):
    def setUp(self):
        self.source = KoreaNTBSource()

    def test_official_ntb_category_maps_to_iso_sector(self):
        item = ET.fromstring(
            """
            <item>
              <stechNum>123</stechNum>
              <techName>Sample technology</techName>
              <tcateNamep>전기/전자</tcateNamep>
              <tcateNamem>반도체</tcateNamem>
            </item>
            """
        )

        technology = self.source._normalize(item)

        self.assertEqual(technology.source_sector, "전기/전자")
        self.assertEqual(technology.sub_sector, "반도체")
        self.assertEqual(technology.sector_codes, ["29", "31"])

    def test_sector_code_filter_accepts_parent_and_exact_codes(self):
        self.assertTrue(self.source._matches_sector_codes(["07.080", "11"], ["07"]))
        self.assertTrue(self.source._matches_sector_codes(["29", "31"], ["31"]))
        self.assertFalse(self.source._matches_sector_codes(["29", "31"], ["65"]))

    def test_korea_source_advertises_sector_filter_support(self):
        self.assertTrue(self.source.sector_filter_supported)


if __name__ == "__main__":
    unittest.main()
