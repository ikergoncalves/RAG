"""Integration tests for embedding generation and Qdrant indexing.

These tests need the Qdrant instance from ``infra/docker-compose.yml`` and are
skipped automatically when it is not reachable (e.g. in the lint-only CI job).
Chunks live in an in-memory SQLite database so no live PostgreSQL is required,
and dense/sparse embeddings are stubbed so the idempotency tests run without any
OpenAI credentials. The one test that exercises real OpenAI embeddings is skipped
when ``OPENAI_API_KEY`` is empty.

Each test runs its async body through ``asyncio.run`` and uses a freshly created
``AsyncQdrantClient`` bound to that loop, plus a unique, disposable collection.
"""

import asyncio
import hashlib
import random
import socket
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import pytest
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.models import Base, Chunk, Document, DocumentStatus
from app.services import indexing, vector_store
from app.services.embeddings.base import EmbeddingProvider


def _qdrant_reachable() -> bool:
    try:
        with socket.create_connection((settings.qdrant_host, settings.qdrant_port), timeout=1.0):
            return True
    except OSError:
        return False


requires_qdrant = pytest.mark.skipif(
    not _qdrant_reachable(),
    reason="Qdrant is not reachable (start infra/docker-compose.yml)",
)
requires_openai = pytest.mark.skipif(
    not settings.openai_api_key,
    reason="OPENAI_API_KEY is not set",
)


# --- Test doubles --------------------------------------------------------


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic dense vectors: identical text -> identical vector."""

    def __init__(self, dimensions: int | None = None) -> None:
        self._dimensions = dimensions or settings.embedding_dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(self._dimensions)]


class FakeSparseEmbedder:
    """Deterministic BM25-style sparse vectors built from token hashes."""

    def embed(self, texts: list[str]) -> list[models.SparseVector]:
        vectors = []
        for text in texts:
            counts: dict[int, float] = {}
            for token in text.lower().split():
                index = int.from_bytes(hashlib.md5(token.encode()).digest()[:4], "big")
                counts[index] = counts.get(index, 0.0) + 1.0
            vectors.append(
                models.SparseVector(indices=list(counts.keys()), values=list(counts.values()))
            )
        return vectors


# --- Fixtures / helpers --------------------------------------------------


def _run(body: Callable[[], Awaitable[None]]) -> None:
    """Run an async test body on a fresh event loop."""
    asyncio.run(body())


async def _make_session_factory() -> tuple[AsyncEngine, async_sessionmaker]:
    """In-memory SQLite engine (single shared connection) with the schema created."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


async def _seed(
    factory: async_sessionmaker, contents: list[str]
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """Insert a document and one chunk per content string; return their ids."""
    document_id = uuid.uuid4()
    chunk_ids = [uuid.uuid4() for _ in contents]
    async with factory() as session:
        session.add(
            Document(
                id=document_id,
                filename="sample.md",
                content_type="text/markdown",
                status=DocumentStatus.indexed.value,
                uploaded_at=datetime.now(timezone.utc),
            )
        )
        session.add_all(
            Chunk(
                id=chunk_ids[index],
                document_id=document_id,
                chunk_index=index,
                content=content,
                token_count=len(content.split()),
                page_number=index + 1,
                section_path="Chapter 1",
                char_start=0,
                char_end=len(content),
            )
            for index, content in enumerate(contents)
        )
        await session.commit()
    return document_id, chunk_ids


async def _embedded_at_values(
    factory: async_sessionmaker, document_id: uuid.UUID
) -> list[datetime | None]:
    async with factory() as session:
        result = await session.execute(
            select(Chunk.embedded_at).where(Chunk.document_id == document_id)
        )
        return [row[0] for row in result.all()]


def _unique_collection() -> str:
    return f"test_chunks_{uuid.uuid4().hex[:12]}"


# --- Tests ---------------------------------------------------------------


@requires_qdrant
def test_indexing_is_idempotent_and_skips_embedded_chunks() -> None:
    async def body() -> None:
        engine, factory = await _make_session_factory()
        client = AsyncQdrantClient(url=settings.qdrant_url)
        collection = _unique_collection()
        document_id, _ = await _seed(factory, ["alpha text", "beta text", "gamma text"])
        try:
            kwargs = dict(
                embedding_provider=FakeEmbeddingProvider(),
                sparse_embedder=FakeSparseEmbedder(),
                collection_name=collection,
                session_factory=factory,
                client=client,
            )

            # First run indexes every chunk and stamps embedded_at.
            first = await indexing.index_document(document_id, **kwargs)
            assert first == 3
            assert await vector_store.count_points(collection, client=client) == 3
            stamps = await _embedded_at_values(factory, document_id)
            assert all(value is not None for value in stamps)

            # Second run finds nothing pending (embedded_at filter) and adds no points.
            second = await indexing.index_document(document_id, **kwargs)
            assert second == 0
            assert await vector_store.count_points(collection, client=client) == 3

            # Forced re-index reprocesses all chunks but upserts by id -> no duplicates.
            forced = await indexing.index_document(document_id, force=True, **kwargs)
            assert forced == 3
            assert await vector_store.count_points(collection, client=client) == 3
        finally:
            await client.delete_collection(collection)
            await client.close()
            await engine.dispose()

    _run(body)


@requires_qdrant
def test_similarity_search_returns_expected_chunk() -> None:
    async def body() -> None:
        engine, factory = await _make_session_factory()
        client = AsyncQdrantClient(url=settings.qdrant_url)
        collection = _unique_collection()
        provider = FakeEmbeddingProvider()
        contents = ["alpha unique passage", "beta unique passage", "gamma unique passage"]
        document_id, chunk_ids = await _seed(factory, contents)
        try:
            await indexing.index_document(
                document_id,
                embedding_provider=provider,
                sparse_embedder=FakeSparseEmbedder(),
                collection_name=collection,
                session_factory=factory,
                client=client,
            )

            query_vector = provider.embed([contents[1]])[0]
            results = await vector_store.search_dense(
                collection, query_vector, limit=1, client=client
            )

            assert results
            assert results[0].id == str(chunk_ids[1])
            assert results[0].payload["content"] == contents[1]
            assert results[0].payload["document_id"] == str(document_id)
            assert results[0].payload["document_filename"] == "sample.md"
        finally:
            await client.delete_collection(collection)
            await client.close()
            await engine.dispose()

    _run(body)


@requires_qdrant
@requires_openai
def test_real_openai_embeddings_similarity_search() -> None:
    async def body() -> None:
        try:
            from app.services.embeddings import OpenAIEmbeddingProvider

            provider = OpenAIEmbeddingProvider()
            sparse = vector_store.get_default_sparse_embedder()
        except Exception as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"Real embedding backends unavailable: {exc}")

        engine, factory = await _make_session_factory()
        client = AsyncQdrantClient(url=settings.qdrant_url)
        collection = _unique_collection()
        contents = [
            "Mitochondria are the powerhouse of the cell and produce ATP.",
            "Qdrant is a vector database used for similarity search.",
        ]
        document_id, chunk_ids = await _seed(factory, contents)
        try:
            await indexing.index_document(
                document_id,
                embedding_provider=provider,
                sparse_embedder=sparse,
                collection_name=collection,
                session_factory=factory,
                client=client,
            )

            query_vector = provider.embed(["What is the powerhouse of the cell?"])[0]
            results = await vector_store.search_dense(
                collection, query_vector, limit=2, client=client
            )

            assert results
            assert results[0].id == str(chunk_ids[0])
        finally:
            await client.delete_collection(collection)
            await client.close()
            await engine.dispose()

    _run(body)
