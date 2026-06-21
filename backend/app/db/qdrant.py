"""Qdrant vector database client (async)."""

from qdrant_client import AsyncQdrantClient

from app.core.config import settings

qdrant_client = AsyncQdrantClient(
    url=settings.qdrant_url,
    api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
    check_compatibility=False,
    # Bound every Qdrant request (seconds) so an unreachable/slow Qdrant fails
    # fast instead of hanging the caller indefinitely.
    timeout=10,
)
