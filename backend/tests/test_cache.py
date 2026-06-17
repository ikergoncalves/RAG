"""Tests for the Redis caches (embeddings + responses).

A small in-memory ``FakeRedis`` stands in for the real client so these run with
no Redis. They cover the cache round-trips and TTLs, query normalization, and
the two behaviours that make the cache worthwhile:

- an embedding cache *hit* skips the embedding provider entirely
  (``RetrievalService`` with the Qdrant calls stubbed), and
- a response cache *hit* replays the answer without calling retrieval or the LLM
  (``ChatService`` over in-memory SQLite).
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.models import Base, Message
from app.services import vector_store
from app.services.cache import CacheService, query_hash
from app.services.chat import ChatService
from app.services.retrieval import RetrievalService

# --- Test doubles --------------------------------------------------------


class FakeRedis:
    """Minimal async Redis stand-in recording values and their TTLs."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value
        self.ttls[key] = ex


class CountingEmbedder:
    """Records how many times ``embed`` is called."""

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class FakeSparse:
    def embed(self, texts: list[str]) -> list[Any]:
        return [object() for _ in texts]


class FakeReranker:
    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list(candidates)


class CountingLLM:
    """LLM double that must never be called on the response-cache-hit path."""

    def __init__(self) -> None:
        self.generate_calls = 0
        self.extract_calls = 0

    async def generate_answer(self, question, context_chunks, *, usage_sink=None):
        self.generate_calls += 1
        if False:  # pragma: no cover - keeps this an async generator
            yield ""

    async def extract_citations(self, question, answer, context_chunks):
        self.extract_calls += 1
        return []


class CountingRetrieval:
    """Retrieval double that must never be called on the response-cache-hit path."""

    def __init__(self) -> None:
        self.calls = 0

    async def retrieve(self, query, top_k: int = 5, filters=None):
        self.calls += 1
        return []


# --- Helpers -------------------------------------------------------------


def _run(body: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(body())


async def _make_session_factory() -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


# --- CacheService round-trips -------------------------------------------


def test_query_embedding_roundtrip_and_ttl() -> None:
    async def body() -> None:
        redis = FakeRedis()
        cache = CacheService(redis)
        await cache.set_query_embedding("What is Qdrant?", [0.5, 0.25, 0.125])

        assert await cache.get_query_embedding("What is Qdrant?") == [0.5, 0.25, 0.125]
        key = "rag:emb:" + query_hash("What is Qdrant?")
        assert redis.ttls[key] == settings.cache_embedding_ttl_seconds

    _run(body)


def test_response_roundtrip_and_ttl() -> None:
    async def body() -> None:
        redis = FakeRedis()
        cache = CacheService(redis)
        payload = {"answer": "A [1].", "citations": [{"number": 1, "chunk_id": "c1"}]}
        await cache.set_response("Tell me about A", payload)

        assert await cache.get_response("Tell me about A") == payload
        key = "rag:resp:" + query_hash("Tell me about A")
        assert redis.ttls[key] == settings.cache_response_ttl_seconds

    _run(body)


def test_normalized_query_shares_cache_entry() -> None:
    """Case/whitespace-different spellings of a query hit the same entry."""

    async def body() -> None:
        cache = CacheService(FakeRedis())
        await cache.set_query_embedding("Hello   World", [1.0, 2.0])
        assert await cache.get_query_embedding("  hello world ") == [1.0, 2.0]

    _run(body)


def test_missing_keys_return_none() -> None:
    async def body() -> None:
        cache = CacheService(FakeRedis())
        assert await cache.get_query_embedding("never cached") is None
        assert await cache.get_response("never cached") is None

    _run(body)


# --- Embedding cache hit skips the provider ------------------------------


def test_embedding_hit_avoids_calling_provider(monkeypatch) -> None:
    """A cached query embedding means the embedding provider is not called."""

    async def body() -> None:
        async def fake_ensure(collection, client=None):
            return None

        async def fake_search(*args, **kwargs):
            return []

        monkeypatch.setattr(vector_store, "ensure_collection", fake_ensure)
        monkeypatch.setattr(vector_store, "search_hybrid", fake_search)

        cache = CacheService(FakeRedis())
        await cache.set_query_embedding("the query", [0.1, 0.2, 0.3, 0.4])

        embedder = CountingEmbedder()
        service = RetrievalService(
            embedding_provider=embedder,
            sparse_embedder=FakeSparse(),
            reranker=FakeReranker(),
            cache_service=cache,
        )

        outcome = await service.retrieve_with_metrics("the query")

        assert embedder.calls == 0  # served from cache
        assert outcome.cache_hit_embedding is True

    _run(body)


def test_embedding_miss_calls_provider_and_populates_cache(monkeypatch) -> None:
    """Without a cached embedding the provider is called and the cache is filled."""

    async def body() -> None:
        async def fake_ensure(collection, client=None):
            return None

        async def fake_search(*args, **kwargs):
            return []

        monkeypatch.setattr(vector_store, "ensure_collection", fake_ensure)
        monkeypatch.setattr(vector_store, "search_hybrid", fake_search)

        cache = CacheService(FakeRedis())
        embedder = CountingEmbedder()
        service = RetrievalService(
            embedding_provider=embedder,
            sparse_embedder=FakeSparse(),
            reranker=FakeReranker(),
            cache_service=cache,
        )

        outcome = await service.retrieve_with_metrics("fresh query")

        assert embedder.calls == 1
        assert outcome.cache_hit_embedding is False
        # The freshly computed vector was written through to the cache.
        assert await cache.get_query_embedding("fresh query") == [0.1, 0.2, 0.3, 0.4]

    _run(body)


# --- Response cache hit skips retrieval + LLM ----------------------------


def test_response_hit_returns_events_without_calling_llm_or_retrieval() -> None:
    async def body() -> None:
        engine, factory = await _make_session_factory()
        citations = [
            {
                "number": 1,
                "chunk_id": "c1",
                "quote": "X is Y.",
                "document_id": "d1",
                "document_name": "doc.md",
                "page": 1,
                "section": "Intro",
            }
        ]
        cache = CacheService(FakeRedis())
        await cache.set_response("What is X?", {"answer": "X is Y [1].", "citations": citations})

        llm = CountingLLM()
        retrieval = CountingRetrieval()
        service = ChatService(
            llm_provider=llm,
            retrieval_service=retrieval,
            session_factory=factory,
            cache_service=cache,
        )

        try:
            # Normalized form matches the cached "What is X?".
            items = [item async for item in service.ask("  what is x? ", None)]

            deltas = [item for item in items if item["type"] == "delta"]
            assert "".join(d["text"] for d in deltas) == "X is Y [1]."

            final = items[-1]
            assert final["type"] == "citations"
            assert final["citations"] == citations
            assert final["conversation_id"]

            # Neither the LLM nor retrieval was touched.
            assert llm.generate_calls == 0
            assert llm.extract_calls == 0
            assert retrieval.calls == 0

            # The cached answer was still persisted as the assistant message.
            async with factory() as session:
                result = await session.execute(select(Message).where(Message.role == "assistant"))
                assistant_messages = list(result.scalars().all())
                assert len(assistant_messages) == 1
                assert assistant_messages[0].content == "X is Y [1]."
                assert assistant_messages[0].citations == citations
        finally:
            await engine.dispose()

    _run(body)
