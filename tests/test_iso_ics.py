import unittest

from backend.taxonomy.iso_ics import (
    ICS_TOP_LEVEL_LABELS,
    OTHER_SECTOR_CODE,
    classify_sector,
    matches_sector_filter,
    top_level_sector_codes,
)


class IsoIcsTaxonomyTests(unittest.TestCase):
    def test_supports_all_40_iso_ics_top_level_fields(self):
        self.assertEqual(len(ICS_TOP_LEVEL_LABELS), 40)
        self.assertEqual(tuple(ICS_TOP_LEVEL_LABELS)[:3], ("01", "03", "07"))
        self.assertEqual(tuple(ICS_TOP_LEVEL_LABELS)[-3:], ("93", "95", "97"))

    def test_maps_official_apctt_label_and_code(self):
        label_result = classify_sector("Telecommunications. Audio and video engineering")
        code_result = classify_sector("33")

        self.assertEqual(label_result.codes, ("33",))
        self.assertEqual(code_result.codes, ("33",))
        self.assertEqual(label_result.confidence, "high")

    def test_maps_source_category_to_iso_ics(self):
        result = classify_sector("Agriculture")

        self.assertEqual(result.codes, ("65",))
        self.assertEqual(result.primary_label, "Agriculture")
        self.assertEqual(result.method, "source_mapping")
        self.assertEqual(result.confidence, "high")

    def test_keeps_cross_sector_source_categories(self):
        result = classify_sector("Electrical & Electronics")

        self.assertEqual(result.codes, ("29", "31"))
        self.assertTrue(matches_sector_filter(result, ["29"]))
        self.assertTrue(matches_sector_filter(result, ["31"]))

    def test_uses_conservative_fallback_for_generic_category(self):
        result = classify_sector(
            "Technology",
            title="Solar-powered irrigation controller",
            summary="A renewable-energy system for agricultural water pumps.",
        )

        self.assertEqual(result.codes, ("27", "65"))
        self.assertEqual(result.method, "keyword_fallback")
        self.assertEqual(result.confidence, "low")

    def test_unclassified_record_is_not_forced_into_a_sector(self):
        result = classify_sector("Technology", title="Novel platform")

        self.assertEqual(result.codes, ())
        self.assertEqual(result.primary_label, "Other / Unclassified")
        self.assertFalse(matches_sector_filter(result, ["35"]))
        self.assertTrue(matches_sector_filter(result, [OTHER_SECTOR_CODE]))

    def test_parent_code_matches_child_ics_code(self):
        result = classify_sector("Biotech")

        self.assertTrue(matches_sector_filter(result, ["07"]))
        self.assertTrue(matches_sector_filter(result, ["07.080"]))
        self.assertEqual(top_level_sector_codes(result), ("07",))


if __name__ == "__main__":
    unittest.main()
