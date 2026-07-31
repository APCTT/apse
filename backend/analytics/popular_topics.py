import os
import re
import sqlite3
import threading
import unicodedata
from datetime import date, timedelta
from pathlib import Path


PREDEFINED_TOPICS = (
    {
        "id": "climate-resilience",
        "label": "Climate resilience",
        "query": "Climate resilience",
        "aliases": ("climate resilience", "climate adaptation"),
    },
    {
        "id": "renewable-energy",
        "label": "Renewable energy",
        "query": "Renewable energy",
        "aliases": ("renewable energy",),
    },
    {
        "id": "artificial-intelligence",
        "label": "AI",
        "query": "Artificial intelligence",
        "aliases": ("ai", "artificial intelligence"),
    },
    {
        "id": "agriculture",
        "label": "Agriculture",
        "query": "Agriculture",
        "aliases": ("agriculture", "agricultural technology"),
    },
    {
        "id": "water-treatment",
        "label": "Water",
        "query": "Water treatment",
        "aliases": ("water", "water treatment"),
    },
    {
        "id": "health-technology",
        "label": "Health technology",
        "query": "Health technology",
        "aliases": ("health technology", "healthcare technology", "health care technology"),
    },
)

_TOPIC_BY_ALIAS = {
    alias: topic["id"]
    for topic in PREDEFINED_TOPICS
    for alias in topic["aliases"]
}


def normalize_query(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").strip().lower()
    return re.sub(r"\s+", " ", normalized)


class PopularTopicStore:
    """Stores daily counts only for an allow-list of predefined topics."""

    def __init__(self, db_path: Path | str | None = None, window_days: int = 30):
        configured_path = os.getenv(
            "SEARCH_ANALYTICS_DB_PATH",
            "backend/cache/search_analytics.db",
        )
        self.db_path = Path(db_path or configured_path)
        self.window_days = max(1, window_days)
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=5)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS popular_topic_daily (
                    topic_id TEXT NOT NULL,
                    day TEXT NOT NULL,
                    search_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (topic_id, day)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_popular_topic_day "
                "ON popular_topic_daily(day)"
            )

    def record_query(self, query: str, on_day: date | None = None) -> bool:
        """Increment a known topic without retaining the submitted query."""
        topic_id = _TOPIC_BY_ALIAS.get(normalize_query(query))
        if topic_id is None:
            return False

        event_day = on_day or date.today()
        cutoff = event_day - timedelta(days=self.window_days - 1)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO popular_topic_daily(topic_id, day, search_count)
                VALUES (?, ?, 1)
                ON CONFLICT(topic_id, day)
                DO UPDATE SET search_count = search_count + 1
                """,
                (topic_id, event_day.isoformat()),
            )
            connection.execute(
                "DELETE FROM popular_topic_daily WHERE day < ?",
                (cutoff.isoformat(),),
            )
        return True

    def ranked_topics(self, today: date | None = None) -> list[dict]:
        end_day = today or date.today()
        start_day = end_day - timedelta(days=self.window_days - 1)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT topic_id, SUM(search_count)
                FROM popular_topic_daily
                WHERE day BETWEEN ? AND ?
                GROUP BY topic_id
                """,
                (start_day.isoformat(), end_day.isoformat()),
            ).fetchall()

        counts = {topic_id: int(count) for topic_id, count in rows}
        ranked = [
            {
                "id": topic["id"],
                "label": topic["label"],
                "query": topic["query"],
                "count": counts.get(topic["id"], 0),
            }
            for topic in PREDEFINED_TOPICS
        ]
        default_order = {topic["id"]: index for index, topic in enumerate(PREDEFINED_TOPICS)}
        ranked.sort(key=lambda topic: (-topic["count"], default_order[topic["id"]]))
        return ranked


popular_topic_store = PopularTopicStore()
