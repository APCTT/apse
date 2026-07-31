import unittest

from backend.taxonomy.iso_ics import classify_sector, matches_sector_filter


class IsoIcsTaxonomyTests(unittest.TestCase):
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

    def test_parent_code_matches_child_ics_code(self):
        result = classify_sector("Biotech")

        self.assertTrue(matches_sector_filter(result, ["07"]))
        self.assertTrue(matches_sector_filter(result, ["07.080"]))


if __name__ == "__main__":
    unittest.main()
