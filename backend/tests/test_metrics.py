"""Tests for the Prometheus metrics helpers and their wiring into ChatService.

Metrics are global, so each test reads a sample value before and after the
action and asserts on the *delta* rather than an absolute value (keeping them
independent of test ordering). The integration test drives a full
``ChatService.ask`` over in-memory SQLite with fakes and asserts every stage
histogram, the cache counters and the cost gauge moved.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.metrics import REGISTRY, add_cost, observe_stage, record_cache, record_request
from app.models import Base
from app.services.cache import CacheService
from app.services.chat import ChatService
from app.services.retrieval import RetrievalOutcome

# --- Test doubles --------------------------------------------------------


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value


class FakeLLM:
    async def generate_answer(self, question, context_chunks, *, usage_sink=None):
        for piece in ("Answer ", "text [1]."):
            yield piece
        if usage_sink is not None:
            usage_sink["prompt_tokens"] = 120
            usage_sink["completion_tokens"] = 30

    async def extract_citations(self, question, answer, context_chunks):
        return []


class StubRetrievalWithMetrics:
    """Returns a fixed outcome with non-zero stage latencies."""

    async def retrieve_with_metrics(self, query, top_k: int = 5, filters=None):
        chunk = {"chunk_id": "c1", "score": 0.4, "rerank_score": 0.9, "content": "X"}
        return RetrievalOutcome(
            candidates=[chunk],
            reranked=[chunk],
            retrieval_ms=12.0,
            rerank_ms=3.0,
            cache_hit_embedding=False,
        )


# --- Helpers -------------------------------------------------------------


def _run(body: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(body())


def _sample(name: str, labels: dict[str, str] | None = None) -> float:
    return REGISTRY.get_sample_value(name, labels or {}) or 0.0


async def _make_session_factory() -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


# --- Helper-level metric tests -------------------------------------------


def test_record_request_increments_counter() -> None:
    labels = {"endpoint": "/chat", "status_code": "200"}
    before = _sample("rag_requests_total", labels)
    record_request("/chat", 200)
    assert _sample("rag_requests_total", labels) == before + 1


def test_observe_stage_increments_histogram_count() -> None:
    labels = {"stage": "retrieval"}
    before = _sample("rag_stage_latency_seconds_count", labels)
    observe_stage("retrieval", 0.02)
    assert _sample("rag_stage_latency_seconds_count", labels) == before + 1


def test_record_cache_tracks_hits_and_misses() -> None:
    hit_labels = {"cache": "embedding", "result": "hit"}
    miss_labels = {"cache": "embedding", "result": "miss"}
    before_hit = _sample("rag_cache_events_total", hit_labels)
    before_miss = _sample("rag_cache_events_total", miss_labels)
    record_cache("embedding", True)
    record_cache("embedding", False)
    assert _sample("rag_cache_events_total", hit_labels) == before_hit + 1
    assert _sample("rag_cache_events_total", miss_labels) == before_miss + 1


def test_add_cost_accumulates_gauge() -> None:
    before = _sample("rag_estimated_cost_usd_total")
    add_cost(0.42)
    assert _sample("rag_estimated_cost_usd_total") == before + 0.42


# --- Integration: a chat request moves the metrics -----------------------


def test_chat_request_records_stage_and_cache_metrics() -> None:
    async def body() -> None:
        engine, factory = await _make_session_factory()

        def stage_count(stage: str) -> float:
            return _sample("rag_stage_latency_seconds_count", {"stage": stage})

        def cache_miss(cache: str) -> float:
            return _sample("rag_cache_events_total", {"cache": cache, "result": "miss"})

        stages = ("retrieval", "rerank", "generation", "total")
        before = {stage: stage_count(stage) for stage in stages}
        before_resp_miss = cache_miss("response")
        before_emb_miss = cache_miss("embedding")
        before_cost = _sample("rag_estimated_cost_usd_total")

        service = ChatService(
            llm_provider=FakeLLM(),
            retrieval_service=StubRetrievalWithMetrics(),
            session_factory=factory,
            cache_service=CacheService(FakeRedis()),
        )

        try:
            items: list[dict[str, Any]] = [
                item async for item in service.ask("How does hybrid search work?", None)
            ]
            assert items[-1]["type"] == "citations"

            for stage in stages:
                assert stage_count(stage) == before[stage] + 1, stage
            assert cache_miss("response") == before_resp_miss + 1
            assert cache_miss("embedding") == before_emb_miss + 1
            # Cost = generation tokens (120/30) + embedding tokens, all > 0.
            assert _sample("rag_estimated_cost_usd_total") > before_cost
        finally:
            await engine.dispose()

    _run(body)
