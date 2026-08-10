import unittest
from unittest.mock import AsyncMock

from backend.sources.apctt import APCTTSource
from backend.taxonomy.apctt_taxonomy import (
    APCTT_COUNTRY_TID_TO_NAME,
    APCTT_SECTOR_TID_TO_ICS,
)
from backend.taxonomy.iso_ics import ICS_TOP_LEVEL_LABELS, OTHER_SECTOR_CODE


def api_record(
    *,
    nid=948,
    country_tid=124,
    sector_tid=298,
    title="Solar-Powered Cold Storage",
):
    return {
        "nid": [{"value": nid}],
        "status": [{"value": True}],
        "langcode": [{"value": "en"}],
        "title": [{"value": title}],
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
    }


class APCTTTaxonomyTests(unittest.TestCase):
    def test_40_iso_sectors_plus_other_map_to_gateway_taxonomy(self):
        self.assertEqual(len(APCTT_SECTOR_TID_TO_ICS), 41)
        self.assertEqual(
            set(APCTT_SECTOR_TID_TO_ICS.values()),
            set(ICS_TOP_LEVEL_LABELS) | {OTHER_SECTOR_CODE},
        )

    def test_supplied_country_tids_are_available(self):
        self.assertEqual(APCTT_COUNTRY_TID_TO_NAME[124], "India")
        self.assertEqual(APCTT_COUNTRY_TID_TO_NAME[138], "Republic of Korea")
        self.assertEqual(APCTT_COUNTRY_TID_TO_NAME[238], "Thailand")
        self.assertEqual(APCTT_COUNTRY_TID_TO_NAME[419], "World Wide")


class APCTTSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_drupal_page_is_deduplicated(self):
        source = APCTTSource()
        record = api_record()
        source._request_page = AsyncMock(side_effect=[[record], [record]])

        items, total = await source.search("", {"page": 1})

        self.assertEqual(total, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(source._request_page.await_count, 2)
        self.assertEqual(items[0].id, "apctt_948")
        self.assertEqual(items[0].country, "India")
        self.assertEqual(items[0].sector_codes, ["87"])
        self.assertEqual(items[0].source_sector, "Paint and colour industries")
        self.assertEqual(items[0].dev_status, "TRL 8 — System complete and qualified")
        self.assertEqual(items[0].url, "https://www.apctt.org/node/948")

    async def test_country_and_sector_filters_use_record_taxonomy(self):
        source = APCTTSource()
        source._request_page = AsyncMock(side_effect=[[api_record()], []])

        matching, matching_total = await source.search(
            "solar", {"page": 1, "country": "India", "sector": "87"}
        )
        wrong_country, wrong_country_total = await source.search(
            "solar", {"page": 1, "country": "Thailand", "sector": "87"}
        )
        wrong_sector, wrong_sector_total = await source.search(
            "solar", {"page": 1, "country": "India", "sector": "65"}
        )

        self.assertEqual((len(matching), matching_total), (1, 1))
        self.assertEqual((wrong_country, wrong_country_total), ([], 0))
        self.assertEqual((wrong_sector, wrong_sector_total), ([], 0))

    async def test_other_tid_remains_explicitly_unclassified(self):
        source = APCTTSource()
        source._request_page = AsyncMock(side_effect=[[api_record(sector_tid=291)], []])

        items, total = await source.search("", {"page": 1, "sector": "other"})

        self.assertEqual(total, 1)
        self.assertEqual(items[0].sector_codes, [])
        self.assertEqual(items[0].sector, "Other / Unclassified")

    async def test_last_successful_catalogue_survives_brief_upstream_failure(self):
        source = APCTTSource()
        record = api_record()
        source._request_page = AsyncMock(side_effect=[[record], [record]])
        await source.search("", {"page": 1})

        source._cache_expires_at = 0
        source._request_page = AsyncMock(side_effect=RuntimeError("temporary outage"))
        items, total = await source.search("", {"page": 1})

        self.assertEqual(total, 1)
        self.assertEqual(items[0].id, "apctt_948")


if __name__ == "__main__":
    unittest.main()
