import unittest
from unittest.mock import patch

from backend.routers.sources import get_facets
from backend.taxonomy.iso_ics import classify_sector


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
    def test_sector_facets_roll_up_to_top_level_and_include_other(self):
        class FakeCatalogue:
            id = "fake"
            name = "Fake catalogue"
            country = "Testland"
            status = "Metadata search"
            transfer_type = ""
            facet_count_supported = True

            def facet_records(self):
                return (
                    {
                        "record": {},
                        "searchable": "biotechnology",
                        "classification": classify_sector("Biotech"),
                    },
                    {
                        "record": {},
                        "searchable": "novel platform",
                        "classification": classify_sector("Technology"),
                    },
                )

        with patch("backend.routers.sources.SOURCES", [FakeCatalogue()]):
            result = facets()

        sectors = {
            item["value"]: (item["label"], item["count"])
            for item in result["sectors"]
        }
        self.assertEqual(
            sectors,
            {
                "07": ("Natural and applied sciences", 1),
                "other": ("Other / Unclassified", 1),
            },
        )
        self.assertNotIn("07.080", sectors)

    def test_counts_follow_the_search_query(self):
        class FakeCatalogue:
            status = "Metadata search"
            transfer_type = ""
            facet_count_supported = True

            def __init__(self, source_id, country, texts):
                self.id = source_id
                self.name = source_id
                self.country = country
                self.texts = texts

            def facet_records(self):
                return (
                    {
                        "record": {},
                        "searchable": text,
                        "classification": classify_sector("Energy"),
                    }
                    for text in self.texts
                )

        catalogues = [
            FakeCatalogue("india", "India", ["solar panel", "wind turbine"]),
            FakeCatalogue("thailand", "Thailand", ["solar dryer"]),
        ]
        with patch("backend.routers.sources.SOURCES", catalogues):
            unfiltered = facets()
            solar = facets(q="solar")

        all_countries = {item["value"]: item["count"] for item in unfiltered["countries"]}
        solar_countries = {item["value"]: item["count"] for item in solar["countries"]}

        self.assertEqual(all_countries, {"India": 2, "Thailand": 1})
        self.assertEqual(solar_countries, {"India": 1, "Thailand": 1})

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
