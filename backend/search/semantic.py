import asyncio
import hashlib
import json
import logging
import math
import re
import sqlite3
import struct
import threading
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import httpx

from backend.config import settings


logger = logging.getLogger(__name__)
_SENSITIVE_RE = re.compile(
    r"(?:https?://|www\.|@|(?:\+?\d[\d ().-]{7,}\d))",
    re.IGNORECASE,
)


def normalize_query(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").strip().lower()
    return re.sub(r"\s+", " ", normalized)


def _query_hash(value: str) -> str:
    return hashlib.sha256(normalize_query(value).encode("utf-8")).hexdigest()


def _content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_vector(values: Iterable[float]) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    magnitude = math.sqrt(sum(value * value for value in vector))
    if not magnitude:
        return vector
    return tuple(value / magnitude for value in vector)


def _pack_vector(values: Iterable[float]) -> bytes:
    vector = tuple(values)
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack_vector(blob: bytes) -> tuple[float, ...]:
    if not blob:
        return ()
    return tuple(struct.unpack(f"<{len(blob) // 4}f", blob))


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_tuple = tuple(left)
    right_tuple = tuple(right)
    if not left_tuple or len(left_tuple) != len(right_tuple):
        return 0.0
    return sum(a * b for a, b in zip(left_tuple, right_tuple))


def searchable_text(record: dict) -> str:
    return " ".join(
        [
            record.get("title", ""),
            record.get("summary", ""),
            record.get("institute", ""),
            " ".join(record.get("keywords", [])),
        ]
    ).strip()


def document_text(record: dict) -> str:
    """Build a bounded public-metadata document for the embedding API."""
    title = record.get("title", "").strip()
    summary = record.get("summary", "").strip()
    institute = record.get("institute", "").strip()
    keywords = ", ".join(record.get("keywords", []))
    text = (
        f"Title: {title}\n"
        f"Summary: {summary}\n"
        f"Keywords: {keywords}\n"
        f"Institution: {institute}"
    )
    # gemini-embedding-001 accepts 2,048 input tokens. This conservative
    # character cap avoids silently losing the identifying title/keywords.
    return text[:6000]


@dataclass(frozen=True)
class SemanticQueryContext:
    query: str
    vector: tuple[float, ...] = ()
    related_terms: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return bool(self.vector or self.related_terms)


class SemanticStore:
    """SQLite cache for vectors and privacy-filtered related terms.

    Query text is never retained. Query vectors and learned relations are
    keyed by a SHA-256 hash of the normalized query.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=10)
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS document_embeddings (
                    source_id TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    model TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    vector BLOB NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (source_id, record_id, model, dimensions)
                );
                CREATE TABLE IF NOT EXISTS query_embeddings (
                    query_hash TEXT NOT NULL,
                    model TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    vector BLOB NOT NULL,
                    expires_at TEXT NOT NULL,
                    PRIMARY KEY (query_hash, model, dimensions)
                );
                CREATE TABLE IF NOT EXISTS related_terms (
                    query_hash TEXT NOT NULL,
                    related_term TEXT NOT NULL,
                    relevance REAL NOT NULL DEFAULT 0,
                    evidence_count INTEGER NOT NULL DEFAULT 1,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY (query_hash, related_term)
                );
                CREATE INDEX IF NOT EXISTS idx_related_terms_query
                ON related_terms(query_hash, relevance DESC);
                CREATE TABLE IF NOT EXISTS api_usage_daily (
                    provider TEXT NOT NULL,
                    usage_day TEXT NOT NULL,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (provider, usage_day)
                );
                """
            )

    def get_query_vector(
        self, query: str, model: str, dimensions: int
    ) -> tuple[float, ...]:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT vector FROM query_embeddings
                WHERE query_hash = ? AND model = ? AND dimensions = ?
                  AND expires_at > ?
                """,
                (_query_hash(query), model, dimensions, now),
            ).fetchone()
        return _unpack_vector(row[0]) if row else ()

    def put_query_vector(
        self,
        query: str,
        model: str,
        dimensions: int,
        vector: Iterable[float],
        cache_days: int = 30,
    ) -> None:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=cache_days)
        ).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO query_embeddings(
                    query_hash, model, dimensions, vector, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(query_hash, model, dimensions)
                DO UPDATE SET vector = excluded.vector,
                              expires_at = excluded.expires_at
                """,
                (
                    _query_hash(query),
                    model,
                    dimensions,
                    _pack_vector(vector),
                    expires_at,
                ),
            )

    def document_hashes(
        self, source_id: str, model: str, dimensions: int
    ) -> dict[str, str]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT record_id, content_hash FROM document_embeddings
                WHERE source_id = ? AND model = ? AND dimensions = ?
                """,
                (source_id, model, dimensions),
            ).fetchall()
        return {record_id: content_hash for record_id, content_hash in rows}

    def put_document_vectors(
        self,
        source_id: str,
        documents: list[tuple[str, str, Iterable[float]]],
        model: str,
        dimensions: int,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                source_id,
                record_id,
                _content_hash(text),
                model,
                dimensions,
                _pack_vector(vector),
                now,
            )
            for record_id, text, vector in documents
        ]
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO document_embeddings(
                    source_id, record_id, content_hash, model, dimensions,
                    vector, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, record_id, model, dimensions)
                DO UPDATE SET content_hash = excluded.content_hash,
                              vector = excluded.vector,
                              updated_at = excluded.updated_at
                """,
                rows,
            )

    def document_vectors(
        self, source_id: str, model: str, dimensions: int
    ) -> dict[str, tuple[float, ...]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT record_id, vector FROM document_embeddings
                WHERE source_id = ? AND model = ? AND dimensions = ?
                """,
                (source_id, model, dimensions),
            ).fetchall()
        return {record_id: _unpack_vector(vector) for record_id, vector in rows}

    def has_document_vectors(self, model: str, dimensions: int) -> bool:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM document_embeddings
                WHERE model = ? AND dimensions = ?
                LIMIT 1
                """,
                (model, dimensions),
            ).fetchone()
        return row is not None

    def related_terms(self, query: str, limit: int = 8) -> tuple[str, ...]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT related_term FROM related_terms
                WHERE query_hash = ? AND evidence_count >= 1
                ORDER BY relevance DESC, evidence_count DESC
                LIMIT ?
                """,
                (_query_hash(query), limit),
            ).fetchall()
        return tuple(row[0] for row in rows)

    def learn_related_terms(
        self, query: str, terms: Iterable[tuple[str, float]]
    ) -> None:
        normalized_query = normalize_query(query)
        if not normalized_query or _SENSITIVE_RE.search(normalized_query):
            return

        safe_terms: list[tuple[str, float]] = []
        for term, relevance in terms:
            normalized = normalize_query(term)
            if (
                normalized
                and normalized != normalized_query
                and 2 <= len(normalized) <= 80
                and len(normalized.split()) <= 8
                and not _SENSITIVE_RE.search(normalized)
            ):
                safe_terms.append((normalized, max(0.0, min(float(relevance), 1.0))))

        now = datetime.now(timezone.utc).isoformat()
        query_hash = _query_hash(query)
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO related_terms(
                    query_hash, related_term, relevance,
                    evidence_count, last_seen_at
                ) VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(query_hash, related_term)
                DO UPDATE SET
                    relevance = MAX(related_terms.relevance, excluded.relevance),
                    evidence_count = related_terms.evidence_count + 1,
                    last_seen_at = excluded.last_seen_at
                """,
                [
                    (query_hash, term, relevance, now)
                    for term, relevance in safe_terms
                ],
            )

    def reserve_api_request(
        self,
        provider: str,
        daily_limit: int,
        on_day: date | None = None,
    ) -> bool:
        """Atomically reserve one request before calling an external API."""
        if daily_limit < 1:
            return False
        usage_day = on_day or datetime.now(
            ZoneInfo("America/Los_Angeles")
        ).date()
        cutoff = usage_day - timedelta(days=45)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT request_count FROM api_usage_daily
                WHERE provider = ? AND usage_day = ?
                """,
                (provider, usage_day.isoformat()),
            ).fetchone()
            current = int(row[0]) if row else 0
            if current >= daily_limit:
                connection.rollback()
                return False
            connection.execute(
                """
                INSERT INTO api_usage_daily(provider, usage_day, request_count)
                VALUES (?, ?, 1)
                ON CONFLICT(provider, usage_day)
                DO UPDATE SET request_count = request_count + 1
                """,
                (provider, usage_day.isoformat()),
            )
            connection.execute(
                "DELETE FROM api_usage_daily WHERE usage_day < ?",
                (cutoff.isoformat(),),
            )
            connection.commit()
        return True

    def api_request_count(
        self, provider: str, on_day: date | None = None
    ) -> int:
        usage_day = on_day or datetime.now(
            ZoneInfo("America/Los_Angeles")
        ).date()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT request_count FROM api_usage_daily
                WHERE provider = ? AND usage_day = ?
                """,
                (provider, usage_day.isoformat()),
            ).fetchone()
        return int(row[0]) if row else 0


class GeminiEmbeddingClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        dimensions: int,
        timeout_seconds: float = 15.0,
    ):
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.timeout_seconds = timeout_seconds
        self.base_url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}"
        )

    async def embed_one(self, text: str, task_type: str) -> tuple[float, ...]:
        payload = {
            "model": f"models/{self.model}",
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
            "outputDimensionality": self.dimensions,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}:embedContent",
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
                json=payload,
            )
            response.raise_for_status()
        return _normalize_vector(response.json()["embedding"]["values"])

    async def embed_many(
        self, texts: list[str], task_type: str, batch_size: int = 50
    ) -> list[tuple[float, ...]]:
        vectors: list[tuple[float, ...]] = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            for offset in range(0, len(texts), batch_size):
                chunk = texts[offset : offset + batch_size]
                payload = {
                    "requests": [
                        {
                            "model": f"models/{self.model}",
                            "content": {"parts": [{"text": text}]},
                            "taskType": task_type,
                            "outputDimensionality": self.dimensions,
                        }
                        for text in chunk
                    ]
                }
                response = await client.post(
                    f"{self.base_url}:batchEmbedContents",
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": self.api_key,
                    },
                    json=payload,
                )
                response.raise_for_status()
                vectors.extend(
                    _normalize_vector(item["values"])
                    for item in response.json()["embeddings"]
                )
                if offset + batch_size < len(texts):
                    await asyncio.sleep(0.15)
        return vectors


class GeminiRelatedTermsClient:
    """Generate a small, validated search expansion for a novel query."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 15.0,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )

    async def expand(self, query: str) -> tuple[str, ...]:
        prompt = (
            "You expand searches for a public Asia-Pacific technology "
            "transfer catalogue. Return 3 to 8 concise English search terms "
            "that are technically synonymous with, closely related to, or "
            "a direct application of the user's query. Preserve technical "
            "meaning; avoid broad generic words, brands, organizations, and "
            "explanations. If the query is not English, include useful English "
            f"equivalents. User query: {query}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 200,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "minItems": 3,
                    "maxItems": 8,
                },
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                self.url,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
                json=payload,
            )
            response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        terms = json.loads(text)
        if not isinstance(terms, list):
            raise ValueError("Gemini related-term response was not a list")
        return tuple(str(term) for term in terms)


class SemanticSearchEngine:
    def __init__(self):
        self.model = settings.SEMANTIC_SEARCH_MODEL
        self.dimensions = settings.SEMANTIC_SEARCH_DIMENSIONS
        self.min_score = settings.SEMANTIC_SEARCH_MIN_SCORE
        self.daily_query_limit = settings.SEMANTIC_SEARCH_DAILY_QUERY_LIMIT
        self.store = SemanticStore(settings.SEMANTIC_SEARCH_DB_PATH)
        self.client = (
            GeminiEmbeddingClient(
                settings.GEMINI_API_KEY,
                self.model,
                self.dimensions,
            )
            if settings.SEMANTIC_SEARCH_ENABLED and settings.GEMINI_API_KEY
            else None
        )
        self.related_client = (
            GeminiRelatedTermsClient(
                settings.GEMINI_API_KEY,
                settings.GEMINI_RELATED_TERMS_MODEL,
            )
            if settings.SEMANTIC_SEARCH_ENABLED and settings.GEMINI_API_KEY
            else None
        )
        self._document_cache: dict[str, dict[str, tuple[float, ...]]] = {}

    async def prepare_query(self, query: str) -> SemanticQueryContext:
        normalized = normalize_query(query)
        if not normalized:
            return SemanticQueryContext(query="")

        related = self.store.related_terms(normalized)
        vector = self.store.get_query_vector(
            normalized, self.model, self.dimensions
        )
        has_document_index = self.store.has_document_vectors(
            self.model, self.dimensions
        )
        needs_api = (
            not vector
            and not related
            and (
                (has_document_index and self.client)
                or (not has_document_index and self.related_client)
            )
        )
        if needs_api:
            reserved = self.store.reserve_api_request(
                "gemini_semantic_query",
                self.daily_query_limit,
            )
            if not reserved:
                logger.info(
                    "Gemini daily query limit reached (%d); using keyword fallback",
                    self.daily_query_limit,
                )
            elif has_document_index and self.client:
                try:
                    vector = await self.client.embed_one(
                        normalized, "RETRIEVAL_QUERY"
                    )
                    self.store.put_query_vector(
                        normalized, self.model, self.dimensions, vector
                    )
                except (httpx.HTTPError, KeyError, ValueError) as exc:
                    logger.warning(
                        "Gemini semantic query failed; using keyword fallback: %s",
                        exc,
                    )
            elif self.related_client:
                try:
                    generated_terms = await self.related_client.expand(
                        normalized
                    )
                    self.store.learn_related_terms(
                        normalized,
                        [(term, 0.65) for term in generated_terms],
                    )
                    related = self.store.related_terms(normalized)
                except (
                    httpx.HTTPError,
                    KeyError,
                    IndexError,
                    ValueError,
                ) as exc:
                    logger.warning(
                        "Gemini related-term expansion failed; "
                        "using keyword fallback: %s",
                        exc,
                    )
        return SemanticQueryContext(
            query=normalized,
            vector=vector,
            related_terms=related,
        )

    def cached_query(self, query: str) -> SemanticQueryContext:
        normalized = normalize_query(query)
        if not normalized:
            return SemanticQueryContext(query="")
        return SemanticQueryContext(
            query=normalized,
            vector=self.store.get_query_vector(
                normalized, self.model, self.dimensions
            ),
            related_terms=self.store.related_terms(normalized),
        )

    def document_vectors(
        self, source_id: str
    ) -> dict[str, tuple[float, ...]]:
        if source_id not in self._document_cache:
            self._document_cache[source_id] = self.store.document_vectors(
                source_id, self.model, self.dimensions
            )
        return self._document_cache[source_id]

    def clear_document_cache(self, source_id: str | None = None) -> None:
        if source_id:
            self._document_cache.pop(source_id, None)
        else:
            self._document_cache.clear()

    def score_record(
        self,
        record: dict,
        context: SemanticQueryContext,
        source_id: str,
    ) -> tuple[bool, float, float]:
        if not context.query:
            return True, 0.0, 0.0

        searchable = normalize_query(searchable_text(record))
        title = normalize_query(record.get("title", ""))
        exact = context.query in searchable
        title_exact = context.query in title
        related_matches = sum(
            1 for term in context.related_terms if term in searchable
        )
        lexical = 1.0 if exact else 0.0
        if title_exact:
            lexical = 1.0
        related_score = min(1.0, related_matches / 2.0)

        semantic = 0.0
        if context.vector:
            record_vector = self.document_vectors(source_id).get(
                str(record.get("id", ""))
            )
            if record_vector:
                semantic = cosine_similarity(context.vector, record_vector)

        matches = exact or related_matches > 0 or semantic >= self.min_score
        score = (
            semantic * 0.60
            + lexical * 0.30
            + related_score * 0.10
            + (0.05 if title_exact else 0.0)
        )
        return matches, score, semantic

    def learn_from_matches(
        self,
        query: str,
        matches: list[tuple[dict, float]],
        limit: int = 8,
    ) -> None:
        """Learn public catalogue keywords from strong semantic matches."""
        candidates: dict[str, float] = {}
        for record, semantic_score in sorted(
            matches, key=lambda item: item[1], reverse=True
        )[:10]:
            if semantic_score < max(self.min_score, 0.62):
                continue
            for keyword in record.get("keywords", []):
                keyword = normalize_query(keyword)
                if keyword:
                    candidates[keyword] = max(
                        candidates.get(keyword, 0.0), semantic_score
                    )
        self.store.learn_related_terms(
            query,
            sorted(
                candidates.items(), key=lambda item: item[1], reverse=True
            )[:limit],
        )

    async def index_source(
        self,
        source_id: str,
        records: list[dict],
        batch_size: int = 50,
    ) -> tuple[int, int]:
        if not self.client:
            raise RuntimeError(
                "GEMINI_API_KEY is required to build the semantic index"
            )

        existing = self.store.document_hashes(
            source_id, self.model, self.dimensions
        )
        pending: list[tuple[str, str]] = []
        for record in records:
            record_id = str(record.get("id", ""))
            text = document_text(record)
            if record_id and existing.get(record_id) != _content_hash(text):
                pending.append((record_id, text))

        indexed = 0
        for offset in range(0, len(pending), batch_size):
            chunk = pending[offset : offset + batch_size]
            vectors = await self.client.embed_many(
                [text for _, text in chunk],
                "RETRIEVAL_DOCUMENT",
                batch_size=batch_size,
            )
            self.store.put_document_vectors(
                source_id,
                [
                    (record_id, text, vector)
                    for (record_id, text), vector in zip(chunk, vectors)
                ],
                self.model,
                self.dimensions,
            )
            indexed += len(chunk)
            logger.info(
                "Semantic index %s: %d/%d updated",
                source_id,
                indexed,
                len(pending),
            )
        self.clear_document_cache(source_id)
        return indexed, len(records)


semantic_search = SemanticSearchEngine()
