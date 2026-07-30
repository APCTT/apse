import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.models.technology import Technology

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent / "cache.db"


def _serialize(value: Any) -> str:
    results, source_totals, failed_sources = value
    return json.dumps({
        "results": [r.model_dump(mode="json") for r in results],
        "source_totals": source_totals,
        "failed_sources": failed_sources,
    }, default=str)


def _deserialize(raw: str) -> Any:
    data = json.loads(raw)
    results = [Technology(**r) for r in data["results"]]
    return results, data["source_totals"], data.get("failed_sources", [])


class TTLCache:
    def __init__(self, db_path: Path = _DB_PATH, max_entries: int = 500):
        self._lock = threading.Lock()
        self._max_entries = max(1, max_entries)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL NOT NULL)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at)"
        )
        self._conn.commit()
        self._purge_expired()
        logger.info("SQLite cache ready at %s", db_path)

    def _purge_expired(self) -> None:
        self._conn.execute("DELETE FROM cache WHERE expires_at <= ?", (time.time(),))
        self._conn.commit()

    def get(self, key: str) -> Any:
        with self._lock:
            row = self._conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            raw, expires_at = row
            if time.time() > expires_at:
                self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                self._conn.commit()
                return None
            try:
                return _deserialize(raw)
            except Exception as e:
                logger.warning("Cache deserialize failed for key %s — %s", key, e)
                self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                self._conn.commit()
                return None

    def set(self, key: str, value: Any, ttl: int = 86400) -> None:
        with self._lock:
            try:
                raw = _serialize(value)
                expires_at = time.time() + ttl
                self._conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                    (key, raw, expires_at),
                )
                self._conn.execute(
                    "DELETE FROM cache WHERE expires_at <= ?", (time.time(),)
                )
                count = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
                excess = count - self._max_entries
                if excess > 0:
                    self._conn.execute(
                        "DELETE FROM cache WHERE key IN "
                        "(SELECT key FROM cache ORDER BY expires_at ASC LIMIT ?)",
                        (excess,),
                    )
                self._conn.commit()
            except Exception as e:
                logger.warning("Cache write failed — %s", e)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._conn.commit()

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cache")
            self._conn.commit()


try:
    cache = TTLCache(max_entries=settings.CACHE_MAX_ENTRIES)
except Exception as _e:
    logger.error("SQLite cache init failed (%s) — falling back to in-memory cache", _e)

    class _MemoryFallback:
        def __init__(self, max_entries=500):
            self._store: dict = {}
            self._lock = threading.Lock()
            self._max_entries = max(1, max_entries)
        def get(self, key):
            with self._lock:
                entry = self._store.get(key)
                if entry is None: return None
                val, exp = entry
                if time.time() > exp:
                    del self._store[key]; return None
                return val
        def set(self, key, value, ttl=86400):
            with self._lock:
                if key not in self._store and len(self._store) >= self._max_entries:
                    self._store.pop(next(iter(self._store)))
                self._store[key] = (value, time.time() + ttl)
        def invalidate(self, key):
            with self._lock: self._store.pop(key, None)
        def clear(self):
            with self._lock: self._store.clear()

    cache = _MemoryFallback(settings.CACHE_MAX_ENTRIES)
