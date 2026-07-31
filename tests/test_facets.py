import unittest

from backend.routers.sources import get_facets


def facets(**overrides):
    params = {
        "q": None,
        "country": None,
        "sector": None,
        "source": None,
        "database_type": None,
    }
    params.update(overrides)
    return get_facets(**params)


class QueryAwareFacetTests(unittest.TestCase):
    def test_counts_follow_the_search_query(self):
        unfiltered = facets()
        solar = facets(q="solar")

        all_countries = {item["value"]: item["count"] for item in unfiltered["countries"]}
        solar_countries = {item["value"]: item["count"] for item in solar["countries"]}

        self.assertEqual(all_countries["India"], 2201)
        self.assertEqual(solar_countries["India"], 45)
        self.assertEqual(solar_countries["Thailand"], 0)

    def test_live_or_redirect_sources_are_not_called_for_counts(self):
        result = facets(q="solar")
        counts = {item["value"]: item["count"] for item in result["sources"]}

        self.assertIsNone(counts["wipo_patentscope"])
        self.assertEqual(counts["csir_india"], 33)

    def test_each_facet_ignores_its_own_selection(self):
        result = facets(q="solar", country="India")
        country_counts = {item["value"]: item["count"] for item in result["countries"]}
        source_counts = {item["value"]: item["count"] for item in result["sources"]}

        self.assertEqual(country_counts["Japan"], 2)
        self.assertEqual(source_counts["jst_japan"], 0)


if __name__ == "__main__":
    unittest.main()
