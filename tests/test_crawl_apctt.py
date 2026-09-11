import unittest
from unittest.mock import AsyncMock, patch

from scripts.crawl_apctt import _format_trl, collect_records, normalize_record


def api_record(*, nid=948, country_tid=124, sector_tid=298, published=True):
    return {
        "nid": [{"value": nid}],
        "status": [{"value": published}],
        "langcode": [{"value": "en"}],
        "title": [{"value": "Solar-Powered Cold Storage"}],
        "created": [{"value": "2026-08-05T05:42:59+00:00"}],
        "path": [{"alias": None}],
        "body": [{"value": "Detailed solar cold-room description."}],
        "field_web_resource_description_": [
            {"value": "Off-grid refrigeration for agricultural produce."}
        ],
        "field_areas_of_application": [{"value": "Farmer cooperatives."}],
        "field_benefits_advantages": [{"value": "Reduces food loss."}],
        "field_cooperation_sought": [{"value": "Pilot partners."}],
        "field_country": [{"target_id": country_tid}],
        "field_page_sectors": [{"target_id": sector_tid}],
        "field_keywords_maximum_5_": [
            {"value": "solar power"},
            {"value": "cold storage"},
        ],
        "field_name_of_organization": [{"value": "Example Institute"}],
        "field_technology_readiness_level": [
            {"value": "trl_8_system_complete_and_qualified"}
        ],
        "field_e_mail": [{"value": "private@example.org"}],
    }


class APCTTCrawlerTests(unittest.IsolatedAsyncioTestCase):
    def test_unknown_trl_is_not_presented_as_a_development_status(self):
        self.assertEqual(_format_trl("not_sure"), "")

    def test_normalizes_taxonomy_and_omits_contact_details(self):
        record = normalize_record(api_record())

        self.assertEqual(record["id"], "apctt_948")
        self.assertEqual(record["countries"], ["India"])
        self.assertEqual(record["sector_codes"], ["87"])
        self.assertEqual(record["sector"], "Paint and colour industries")
        self.assertEqual(record["trl"], "TRL 8 — System complete and qualified")
        self.assertIn("Pilot partners", record["search_text"])
        self.assertNotIn("e_mail", record)
        self.assertNotIn("private@example.org", str(record))

    def test_other_tid_is_explicitly_unclassified(self):
        record = normalize_record(api_record(sector_tid=291))

        self.assertEqual(record["sector_codes"], [])
        self.assertEqual(record["sector_code"], "other")

    async def test_repeated_drupal_page_is_deduplicated(self):
        record = api_record()
        with patch(
            "scripts.crawl_apctt.fetch_page",
            new=AsyncMock(side_effect=[[record], [record]]),
        ) as request:
            records, discovered, failed = await collect_records(object())

        self.assertEqual(len(records), 1)
        self.assertEqual((discovered, failed), (1, 0))
        self.assertEqual(request.await_count, 2)

    async def test_unpublished_records_are_not_indexed(self):
        with patch(
            "scripts.crawl_apctt.fetch_page",
            new=AsyncMock(side_effect=[[api_record(published=False)], []]),
        ):
            records, discovered, failed = await collect_records(object())

        self.assertEqual(records, [])
        self.assertEqual((discovered, failed), (0, 0))


if __name__ == "__main__":
    unittest.main()
