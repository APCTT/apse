import asyncio
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from backend.search.semantic import (
    SemanticSearchEngine,
    SemanticStore,
    cosine_similarity,
    normalize_query,
)


class SemanticStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "semantic.db"
        self.store = SemanticStore(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_query_vectors_are_cached_without_raw_query_text(self):
        self.store.put_query_vector(
            "Solar-powered irrigation",
            "test-model",
            3,
            (0.1, 0.2, 0.3),
        )

        cached = self.store.get_query_vector(
            "  solar-powered   irrigation ",
            "test-model",
            3,
        )
        self.assertEqual(len(cached), 3)

        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT query_hash FROM query_embeddings"
            ).fetchone()
        self.assertNotIn("solar", row[0])
        self.assertEqual(len(row[0]), 64)

    def test_sensitive_queries_do_not_learn_related_terms(self):
        self.store.learn_related_terms(
            "private.user@example.com",
            [("solar pump", 0.9)],
        )
        self.assertEqual(
            self.store.related_terms("private.user@example.com"),
            (),
        )

    def test_safe_public_metadata_terms_accumulate(self):
        self.store.learn_related_terms(
            "solar irrigation",
            [("photovoltaic water pump", 0.72)],
        )
        self.store.learn_related_terms(
            "solar irrigation",
            [("photovoltaic water pump", 0.81)],
        )

        self.assertEqual(
            self.store.related_terms("solar irrigation"),
            ("photovoltaic water pump",),
        )
        with sqlite3.connect(self.db_path) as connection:
            evidence, relevance = connection.execute(
                "SELECT evidence_count, relevance FROM related_terms"
            ).fetchone()
        self.assertEqual(evidence, 2)
        self.assertEqual(relevance, 0.81)

    def test_expired_query_data_is_physically_deleted(self):
        old = datetime(2026, 6, 1, tzinfo=timezone.utc)
        current = datetime(2026, 8, 4, tzinfo=timezone.utc)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO query_embeddings(
                    query_hash, model, dimensions, vector, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("a" * 64, "test-model", 1, b"\x00\x00\x00\x00", old.isoformat()),
            )
            connection.execute(
                """
                INSERT INTO related_terms(
                    query_hash, related_term, relevance,
                    evidence_count, last_seen_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("a" * 64, "old term", 0.5, 1, old.isoformat()),
            )

        deleted_vectors, deleted_terms = self.store.purge_expired_query_data(
            now=current,
            force=True,
        )
        self.assertEqual((deleted_vectors, deleted_terms), (1, 1))

    def test_cosine_similarity_uses_normalized_vectors(self):
        self.assertAlmostEqual(
            cosine_similarity((1.0, 0.0), (0.8, 0.6)),
            0.8,
        )

    def test_query_normalization_is_stable(self):
        self.assertEqual(
            normalize_query("  Renewable   ENERGY "),
            "renewable energy",
        )

    def test_daily_api_limit_is_atomic_and_resets_next_day(self):
        today = date(2026, 8, 3)
        self.assertTrue(
            self.store.reserve_api_request("gemini", 2, today)
        )
        self.assertTrue(
            self.store.reserve_api_request("gemini", 2, today)
        )
        self.assertFalse(
            self.store.reserve_api_request("gemini", 2, today)
        )
        self.assertEqual(self.store.api_request_count("gemini", today), 2)
        self.assertTrue(
            self.store.reserve_api_request(
                "gemini",
                2,
                today + timedelta(days=1),
            )
        )

    def test_related_terms_are_generated_once_then_reused(self):
        class FakeRelatedClient:
            def __init__(self):
                self.calls = 0

            async def expand(self, query):
                self.calls += 1
                return ("photovoltaic water pump", "off-grid irrigation")

        engine = SemanticSearchEngine()
        engine.store = self.store
        engine.client = None
        engine.related_client = FakeRelatedClient()
        engine.daily_query_limit = 800

        first = asyncio.run(engine.prepare_query("solar irrigation"))
        second = asyncio.run(engine.prepare_query("solar irrigation"))

        self.assertEqual(engine.related_client.calls, 1)
        self.assertEqual(first.related_terms, second.related_terms)
        self.assertIn("photovoltaic water pump", second.related_terms)
        self.assertEqual(
            self.store.api_request_count("gemini_semantic_query"),
            1,
        )

    def test_concurrent_identical_queries_share_one_api_request(self):
        class SlowRelatedClient:
            def __init__(self):
                self.calls = 0

            async def expand(self, query):
                self.calls += 1
                await asyncio.sleep(0.02)
                return ("photovoltaic water pump", "off-grid irrigation")

        engine = SemanticSearchEngine()
        engine.store = self.store
        engine.client = None
        engine.related_client = SlowRelatedClient()
        engine.daily_query_limit = 800

        async def run_concurrently():
            return await asyncio.gather(
                engine.prepare_query("solar irrigation"),
                engine.prepare_query(" Solar   Irrigation "),
                engine.prepare_query("solar irrigation"),
            )

        contexts = asyncio.run(run_concurrently())

        self.assertEqual(engine.related_client.calls, 1)
        self.assertEqual(len(contexts), 3)
        self.assertTrue(all(context.related_terms for context in contexts))
        self.assertEqual(
            self.store.api_request_count("gemini_semantic_query"),
            1,
        )


if __name__ == "__main__":
    unittest.main()
