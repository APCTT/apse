import unittest
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock

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
              <tcateCodep>20</tcateCodep>
              <tcateCodem>ED</tcateCodem>
              <tcateNamep>전기/전자</tcateNamep>
              <tcateNamem>반도체</tcateNamem>
            </item>
            """
        )

        technology = self.source._normalize(item)

        self.assertEqual(technology.source_sector, "전기/전자")
        self.assertEqual(technology.sub_sector, "반도체")
        self.assertEqual(technology.sector_codes, ["29", "31"])
        self.assertEqual(technology.classification_method, "ntb_code_mapping")

    def test_sector_code_filter_accepts_parent_and_exact_codes(self):
        self.assertTrue(self.source._matches_sector_codes(["07.080", "11"], ["07"]))
        self.assertTrue(self.source._matches_sector_codes(["29", "31"], ["31"]))
        self.assertFalse(self.source._matches_sector_codes(["29", "31"], ["65"]))

    def test_korea_source_advertises_sector_filter_support(self):
        self.assertTrue(self.source.sector_filter_supported)


class KoreaNTBSearchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.source = KoreaNTBSource()

    async def test_sector_filter_is_sent_to_ntb_as_native_code(self):
        self.source._request = AsyncMock(
            return_value=ET.fromstring(
                """
                <response>
                  <header><resultCode>00</resultCode></header>
                  <body>
                    <totalCount>321</totalCount>
                    <items>
                      <item>
                        <stechNum>123</stechNum>
                        <techName>Sample technology</techName>
                        <tcateCodep>20</tcateCodep>
                        <tcateCodem>ED</tcateCodem>
                        <tcateNamep>전기/전자</tcateNamep>
                        <tcateNamem>반도체</tcateNamem>
                      </item>
                    </items>
                  </body>
                </response>
                """
            )
        )

        items, total = await self.source.search("", {"sector": "31", "page": 2})

        self.assertEqual(total, 321)
        self.assertEqual(len(items), 1)
        params = self.source._request.await_args.args[0]
        self.assertEqual(params["tcateCode"], "ED")
        self.assertEqual(params["pageNo"], "2")
        self.assertEqual(params["numOfRows"], "20")

    async def test_unmapped_gateway_sector_skips_ntb_request(self):
        self.source._request = AsyncMock()

        items, total = await self.source.search("", {"sector": "95", "page": 1})

        self.assertEqual((items, total), ([], 0))
        self.source._request.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
