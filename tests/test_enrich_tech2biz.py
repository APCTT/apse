import unittest

from scripts.enrich_tech2biz import (
    build_prompt,
    enrich_record,
    load_overrides,
    parse_response,
    response_schema,
    validate_enriched,
)


class Tech2BizEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "id": "tech2biz_1",
            "tech_id": "1",
            "title": "ชื่อ",
            "summary": "รายละเอียด",
            "title_original": "ชื่อ",
            "summary_original": "รายละเอียด",
            "url": "https://www.tech2biz.net/content/1-example",
        }
        self.result = {
            "id": "tech2biz_1",
            "title_en": "Fruit coating",
            "summary_en": "A natural coating designed to extend fruit shelf life.",
            "sector_code": "67",
            "confidence": "high",
            "reason": "Food preservation technology",
        }

    def test_prompt_contains_all_top_level_codes_and_untrusted_data_warning(self):
        prompt = build_prompt([self.source])
        self.assertIn("01:", prompt)
        self.assertIn("97:", prompt)
        self.assertIn("other:", prompt)
        self.assertIn("untrusted source data", prompt)
        self.assertIn("do not place animal feed in 67", prompt)
        self.assertIn("cosmetic or personal-care formulations in", prompt)

    def test_schema_restricts_sector_codes(self):
        schema = response_schema()
        enum = schema["properties"]["items"]["items"]["properties"]["sector_code"]["enum"]
        self.assertEqual(41, len(enum))
        self.assertIn("67", enum)
        self.assertIn("other", enum)

    def test_structured_response_is_reordered_to_requested_ids(self):
        second = dict(self.result, id="tech2biz_2")
        response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": __import__("json").dumps({
                            "items": [second, self.result],
                        }),
                    }],
                },
            }],
        }
        parsed = parse_response(response, ["tech2biz_1", "tech2biz_2"])
        self.assertEqual(["tech2biz_1", "tech2biz_2"], [item["id"] for item in parsed])

    def test_enriched_record_preserves_original_and_uses_official_label(self):
        enriched = enrich_record(self.source, self.result)
        self.assertEqual("Fruit coating", enriched["title"])
        self.assertEqual("ชื่อ", enriched["title_original"])
        self.assertEqual("Food technology", enriched["sector"])
        self.assertEqual("67", enriched["sector_code"])

    def test_validation_accepts_complete_enrichment(self):
        enriched = enrich_record(self.source, self.result)
        self.assertEqual([], validate_enriched([self.source], [enriched]))

    def test_reviewed_override_replaces_model_sector(self):
        enriched = enrich_record(
            self.source,
            self.result,
            {
                "tech2biz_1": {
                    "sector_code": "65",
                    "reason": "Reviewed as animal feed technology",
                },
            },
        )
        self.assertEqual("65", enriched["sector_code"])
        self.assertEqual("Agriculture", enriched["sector"])
        self.assertEqual("reviewed_override", enriched["classification_method"])
        self.assertEqual("high", enriched["classification_confidence"])

    def test_repository_override_table_is_valid(self):
        overrides = load_overrides()
        self.assertIn("tech2biz_1498", overrides)
        self.assertEqual("97", overrides["tech2biz_1498"]["sector_code"])


if __name__ == "__main__":
    unittest.main()
