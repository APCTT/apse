import unittest

from backend.sources.registry import SOURCE_MAP


class SourceRegistryTests(unittest.TestCase):
    def test_ip_australia_is_not_an_active_source(self):
        self.assertNotIn("ip_australia", SOURCE_MAP)

    def test_malaysia_commercialisation_portal_is_active(self):
        self.assertIn("malaysia_rd_portal", SOURCE_MAP)


if __name__ == "__main__":
    unittest.main()
