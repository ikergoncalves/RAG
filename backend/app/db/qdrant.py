"""Qdrant vector database client (async)."""

from qdrant_client import AsyncQdrantClient

from app.core.config import settings

qdrant_client = AsyncQdrantClient(url=settings.qdrant_url)
