import unittest

from scripts.enrich_malaysia_rd_portal import (
    enrich_record,
    parse_response,
    validate_enriched,
)


class MalaysiaPortalEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "id": "malaysia_rd_example",
            "title": "Smart Irrigation",
            "summary": "Sistem ini menggunakan sensor untuk mengawal penggunaan air.",
            "keywords": ["MySTI", "Agriculture"],
            "url": "https://example.test/record",
        }

    def test_parse_response_requires_translation_for_malay_field(self):
        response = {
            "candidates": [{"content": {"parts": [{"text": """
                {"items":[{
                  "id":"malaysia_rd_example",
                  "title_language":"english",
                  "summary_language":"malay",
                  "title_en":"",
                  "summary_en":"This system uses sensors to control water use."
                }]}
            """}]}}]
        }
        items = parse_response(response, ["malaysia_rd_example"])
        self.assertEqual(items[0]["summary_language"], "malay")

    def test_enrich_record_translates_only_malay_field_and_preserves_original(self):
        result = {
            "id": "malaysia_rd_example",
            "title_language": "english",
            "summary_language": "malay",
            "title_en": "",
            "summary_en": "This system uses sensors to control water use.",
        }
        item = enrich_record(self.source, result)
        self.assertEqual(item["title"], "Smart Irrigation")
        self.assertNotIn("title_original", item)
        self.assertEqual(item["summary_original"], self.source["summary"])
        self.assertEqual(item["summary_translation_status"], "translated_gemini")
        self.assertEqual(item["language"], "Malay")

    def test_english_record_remains_untouched(self):
        source = dict(self.source, summary="This system uses sensors to control water use.")
        result = {
            "id": "malaysia_rd_example",
            "title_language": "english",
            "summary_language": "english",
            "title_en": "",
            "summary_en": "",
        }
        item = enrich_record(source, result)
        self.assertEqual(item["title"], source["title"])
        self.assertEqual(item["summary"], source["summary"])
        self.assertEqual(item["language"], "English")
        self.assertNotIn("summary_translation_status", item)
        self.assertEqual(validate_enriched([source], [item]), [])


if __name__ == "__main__":
    unittest.main()
