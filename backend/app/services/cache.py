"""Redis caching for query embeddings and full responses.

Two caches, both keyed by a SHA-256 hash of the *normalized* query (lower-cased,
whitespace-collapsed) so that trivially different spellings of the same question
share an entry:

- **Query embeddings** — the dense vector for a query. Looked up by
  :class:`~app.services.retrieval.service.RetrievalService` before calling the
  embedding provider, so a repeated query skips the paid embedding API call.
- **Responses** — the full ``{"answer", "citations"}`` payload for a query.
  Looked up by :class:`~app.services.chat.ChatService` before retrieval, so an
  identical question is answered without touching retrieval or the LLM.

All Redis access is best-effort: a connection/serialization error is logged and
treated as a cache miss, so the cache can never take the request path down.
"""

import hashlib
import json
import logging
import re
from typing import Any

from app.core.config import settings
from app.db.redis import redis_client

logger = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")
_EMBEDDING_PREFIX = "rag:emb:"
_RESPONSE_PREFIX = "rag:resp:"


def _normalize(query: str) -> str:
    """Lower-case and collapse whitespace so equivalent queries hash equally."""
    return _WHITESPACE.sub(" ", query.strip().lower())


def query_hash(query: str) -> str:
    """Return the SHA-256 hex digest of the normalized ``query``."""
    return hashlib.sha256(_normalize(query).encode("utf-8")).hexdigest()


class CacheService:
    """Best-effort Redis cache for query embeddings and responses."""

    def __init__(self, client: Any = None) -> None:
        self._client = client if client is not None else redis_client

    # --- Query embeddings ------------------------------------------------

    async def get_query_embedding(self, query: str) -> list[float] | None:
        """Return the cached dense embedding for ``query``, or ``None`` on miss."""
        raw = await self._safe_get(_EMBEDDING_PREFIX + query_hash(query))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("Discarding malformed cached embedding for query")
            return None

    async def set_query_embedding(
        self, query: str, vector: list[float], ttl: int | None = None
    ) -> None:
        """Cache the dense ``vector`` for ``query`` with the embedding TTL."""
        ttl = ttl if ttl is not None else settings.cache_embedding_ttl_seconds
        await self._safe_set(_EMBEDDING_PREFIX + query_hash(query), json.dumps(vector), ttl)

    # --- Responses -------------------------------------------------------

    async def get_response(self, query: str) -> dict[str, Any] | None:
        """Return the cached ``{answer, citations}`` for ``query``, or ``None``."""
        raw = await self._safe_get(_RESPONSE_PREFIX + query_hash(query))
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("Discarding malformed cached response for query")
            return None
        return payload if isinstance(payload, dict) else None

    async def set_response(
        self, query: str, payload: dict[str, Any], ttl: int | None = None
    ) -> None:
        """Cache the full ``payload`` for ``query`` with the response TTL."""
        ttl = ttl if ttl is not None else settings.cache_response_ttl_seconds
        await self._safe_set(_RESPONSE_PREFIX + query_hash(query), json.dumps(payload), ttl)

    # --- Best-effort Redis access ----------------------------------------

    async def _safe_get(self, key: str) -> str | None:
        try:
            return await self._client.get(key)
        except Exception as exc:  # pragma: no cover - depends on Redis availability
            logger.warning("Cache get failed for %s: %s", key, exc)
            return None

    async def _safe_set(self, key: str, value: str, ttl: int) -> None:
        try:
            await self._client.set(key, value, ex=ttl)
        except Exception as exc:  # pragma: no cover - depends on Redis availability
            logger.warning("Cache set failed for %s: %s", key, exc)


_default_cache: CacheService | None = None


def get_default_cache() -> CacheService:
    """Return the shared cache service (backed by the app-wide Redis client)."""
    global _default_cache
    if _default_cache is None:
        _default_cache = CacheService()
    return _default_cache
