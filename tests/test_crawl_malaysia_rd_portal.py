import unittest

from scripts.crawl_malaysia_rd_portal import parse_products


class MalaysiaRDPortalCrawlerTests(unittest.TestCase):
    def test_parser_omits_contact_fields_and_maps_public_metadata(self):
        payload = [{
            "Product Name": "Smart Solar Irrigation",
            "Product Description": "A solar-powered irrigation controller.",
            "Company Name": "Example Research Institute",
            "Business Email": "private@example.test",
            "Business Address": "Example address",
            "Category": "Agriculture,Renewable Energy",
            "Programme": "MySTI",
            "Cover Image": "https://example.test/image.jpg",
        }]

        records, discovered, invalid = parse_products(payload)

        self.assertEqual((discovered, invalid), (1, 0))
        self.assertEqual(len(records), 1)
        item = records[0]
        self.assertEqual(item["title"], "Smart Solar Irrigation")
        self.assertEqual(item["institute"], "Example Research Institute")
        self.assertEqual(item["sector_codes"], ["65", "27"])
        self.assertEqual(item["programme"], "MySTI")
        self.assertEqual(item["url"], "https://commercialisation.mosti.gov.my/rd-products/0")
        self.assertNotIn("Business Email", item)
        self.assertNotIn("Business Address", item)
        self.assertNotIn("Cover Image", item)
        self.assertNotIn("private@example.test", str(item))

    def test_duplicate_title_and_provider_pair_is_collapsed(self):
        payload = [
            {
                "Product Name": "Same Product",
                "Product Description": "Short description.",
                "Company Name": "Same Provider",
                "Category": "Special",
                "Programme": "MCY",
            },
            {
                "Product Name": "Same Product",
                "Product Description": "A longer and more useful product description.",
                "Company Name": "Same Provider",
                "Category": "Special",
                "Programme": "MCY",
            },
        ]

        records, discovered, invalid = parse_products(payload)

        self.assertEqual((discovered, invalid), (2, 0))
        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0]["summary"],
            "A longer and more useful product description.",
        )
        self.assertEqual(records[0]["url"], "https://commercialisation.mosti.gov.my/rd-products/1")

    def test_invalid_records_are_counted_not_indexed(self):
        records, discovered, invalid = parse_products([
            {"Product Name": "Missing provider and description"},
            None,
        ])

        self.assertEqual(records, [])
        self.assertEqual((discovered, invalid), (2, 2))

    def test_mojibake_in_portal_text_is_repaired(self):
        records, _, _ = parse_products([{
            "Product Name": "GEC‚Äôs Composting Machine¬Æ",
            "Product Description": "Fast‚Äîand reliable\\ \\ processing by Woc‚âà√áawek.",
            "Company Name": "Example Sdn Bhd",
            "Category": "Environmental and Green Technology",
            "Programme": "MySTI",
        }])

        self.assertEqual(records[0]["title"], "GEC’s Composting Machine®")
        self.assertEqual(records[0]["summary"], "Fast—and reliable processing by Wocławek.")


if __name__ == "__main__":
    unittest.main()
