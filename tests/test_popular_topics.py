import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from backend.analytics.popular_topics import PopularTopicStore


class PopularTopicStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "analytics.db"
        self.store = PopularTopicStore(self.db_path, window_days=30)
        self.today = date(2026, 7, 31)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_only_allowlisted_topics_are_recorded(self):
        self.assertTrue(self.store.record_query("  AI  ", self.today))
        self.assertFalse(self.store.record_query("private.user@example.com", self.today))

        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT topic_id, search_count FROM popular_topic_daily"
            ).fetchall()

        self.assertEqual(rows, [("artificial-intelligence", 1)])

    def test_last_thirty_days_determine_the_ranking(self):
        self.store.record_query("Renewable energy", self.today)
        self.store.record_query("Renewable energy", self.today)
        self.store.record_query("Water treatment", self.today - timedelta(days=29))
        self.store.record_query("Water treatment", self.today - timedelta(days=30))

        ranked = self.store.ranked_topics(self.today)

        self.assertEqual(ranked[0]["id"], "renewable-energy")
        self.assertEqual(ranked[0]["count"], 2)
        water = next(topic for topic in ranked if topic["id"] == "water-treatment")
        self.assertEqual(water["count"], 1)

    def test_zero_count_topics_keep_the_editorial_default_order(self):
        ranked = self.store.ranked_topics(self.today)
        self.assertEqual(
            [topic["id"] for topic in ranked],
            [
                "climate-resilience",
                "renewable-energy",
                "artificial-intelligence",
                "agriculture",
                "water-treatment",
                "health-technology",
            ],
        )


if __name__ == "__main__":
    unittest.main()
