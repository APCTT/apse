import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from backend.sources.apctt import APCTTLiveSource, APCTTSource, create_apctt_source
from backend.taxonomy.apctt_taxonomy import (
    APCTT_COUNTRY_TID_TO_NAME,
    APCTT_SECTOR_TID_TO_ICS,
)
from backend.taxonomy.iso_ics import ICS_TOP_LEVEL_LABELS, OTHER_SECTOR_CODE


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
    @staticmethod
    def _live_record():
        return {
            "nid": [{"value": 948}],
            "status": [{"value": True}],
            "langcode": [{"value": "en"}],
            "title": [{"value": "Solar-Powered Cold Storage"}],
            "created": [{"value": "2026-08-05T05:42:59+00:00"}],
            "path": [{"alias": None}],
            "field_web_resource_description_": [
                {"value": "Off-grid refrigeration for agricultural produce."}
            ],
            "field_country": [{"target_id": 124}],
            "field_page_sectors": [{"target_id": 278}],
            "field_keywords_maximum_5_": [{"value": "cold storage"}],
            "field_name_of_organization": [{"value": "Example Institute"}],
        }

    async def test_bundled_snapshot_is_searchable_without_live_api(self):
        source = APCTTSource()

        items, total = await source.search(
            "antiviral", {"page": 1, "country": "Thailand", "sector": "11"}
        )

        self.assertGreaterEqual(total, 1)
        self.assertEqual(items[0].source_id, "apctt")
        self.assertEqual(items[0].country, "Thailand")
        self.assertEqual(items[0].sector_codes, ["11"])
        self.assertEqual(items[0].source_sector, "Health care technology")
        self.assertTrue(items[0].url.startswith("https://www.apctt.org/node/"))

    async def test_country_and_sector_filters_use_record_metadata(self):
        source = APCTTSource()

        matching, matching_total = await source.search(
            "antiviral", {"page": 1, "country": "Thailand", "sector": "11"}
        )
        wrong_country, wrong_country_total = await source.search(
            "antiviral", {"page": 1, "country": "India", "sector": "11"}
        )
        wrong_sector, wrong_sector_total = await source.search(
            "antiviral", {"page": 1, "country": "Thailand", "sector": "65"}
        )

        self.assertEqual((len(matching), matching_total), (1, 1))
        self.assertEqual((wrong_country, wrong_country_total), ([], 0))
        self.assertEqual((wrong_sector, wrong_sector_total), ([], 0))

    async def test_discovery_only_text_is_searchable_but_card_summary_stays_short(self):
        record = {
            "id": "apctt_1",
            "title": "Compact title",
            "summary": "Short public summary.",
            "search_text": "Short public summary. Specialized pilot cooperation.",
            "institute": "Example Institute",
            "sector": "Other Technologies n.e.c.",
            "sector_code": "other",
            "classification_method": "apctt_taxonomy_tid",
            "classification_confidence": "high",
            "keywords": [],
            "countries": ["India", "Thailand"],
            "language": "en",
            "reg_date": "2026-09-09",
            "url": "https://www.apctt.org/node/1",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "apctt.json"
            path.write_text(json.dumps([record]), encoding="utf-8")
            source = APCTTSource()
            source._data_path = path

            items, total = await source.search(
                "specialized", {"page": 1, "country": "India", "sector": "other"}
            )

        self.assertEqual(total, 1)
        self.assertEqual(items[0].summary, "Short public summary.")
        self.assertEqual(items[0].country, "India, Thailand")
        self.assertEqual(items[0].reg_date, "2026-09-09")

    def test_snapshot_contains_no_contact_fields_or_dummy_records(self):
        path = Path(__file__).parent.parent / "backend" / "sources" / "data" / "apctt.json"
        records = json.loads(path.read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(records), 1)
        serialized = json.dumps(records).lower()
        self.assertNotIn("field_e_mail", serialized)
        self.assertNotIn("dummy data for testing", serialized)

    def test_source_is_reported_as_reviewed_snapshot(self):
        source = APCTTSource()

        self.assertEqual(source.access_method, "Reviewed APCTT catalogue snapshot")
        self.assertTrue(source.facet_count_supported)
        self.assertFalse(source.requires_facet_preparation)

    def test_factory_preserves_snapshot_and_live_modes(self):
        self.assertIs(type(create_apctt_source("snapshot")), APCTTSource)
        self.assertIs(type(create_apctt_source("live")), APCTTLiveSource)

    async def test_live_mode_loads_the_upstream_catalogue(self):
        source = APCTTLiveSource()
        source._request_page = AsyncMock(
            side_effect=[[self._live_record()], []]
        )

        items, total = await source.search("cold storage", {"page": 1})

        self.assertEqual(total, 1)
        self.assertEqual(items[0].country, "India")
        self.assertEqual(items[0].sector_codes, ["67"])
        self.assertEqual(source._request_page.await_count, 2)

    async def test_live_mode_falls_back_to_reviewed_snapshot(self):
        source = APCTTLiveSource()
        source._request_page = AsyncMock(side_effect=RuntimeError("blocked"))

        items, total = await source.search("antiviral", {"page": 1})

        self.assertGreaterEqual(total, 1)
        self.assertEqual(items[0].source_id, "apctt")


if __name__ == "__main__":
    unittest.main()
