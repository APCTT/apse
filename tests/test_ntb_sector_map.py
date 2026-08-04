import unittest

from backend.taxonomy.ntb_sector_map import (
    ICS_TO_NTB_QUERY_CODE,
    NTB_CODE_TO_ICS,
    classify_ntb_sector,
    ntb_query_codes_for_ics,
)


class NTBSectorMapTests(unittest.TestCase):
    def test_mapping_table_covers_all_official_unique_codes(self):
        self.assertEqual(len(NTB_CODE_TO_ICS), 52)

    def test_specific_middle_code_takes_priority_over_broad_primary_code(self):
        result = classify_ntb_sector(
            primary_code="50",
            middle_code="LA",
            primary_name="바이오ㆍ의료",
            middle_name="생명과학",
        )

        self.assertEqual(result.codes, ("07.080",))
        self.assertEqual(result.method, "ntb_code_mapping")
        self.assertEqual(result.confidence, "high")

    def test_exact_official_label_is_fallback_for_legacy_response(self):
        result = classify_ntb_sector(primary_name="에너지/자원")

        self.assertEqual(result.codes, ("27",))
        self.assertEqual(result.method, "ntb_label_mapping")

    def test_reverse_map_uses_specific_ntb_query_codes(self):
        self.assertEqual(ntb_query_codes_for_ics(["31"]), ("ED",))
        self.assertEqual(ntb_query_codes_for_ics(["07"]), ("LA",))
        self.assertEqual(ntb_query_codes_for_ics(["65", "67"]), ("LB",))

    def test_every_reverse_mapping_points_to_a_known_ntb_code(self):
        self.assertTrue(ICS_TO_NTB_QUERY_CODE)
        self.assertTrue(
            all(code in NTB_CODE_TO_ICS for code in ICS_TO_NTB_QUERY_CODE.values())
        )


if __name__ == "__main__":
    unittest.main()
