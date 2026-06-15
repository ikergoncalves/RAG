"""Tests for hybrid retrieval (dense + BM25/RRF) and cross-encoder re-ranking.

Layering mirrors ``test_indexing.py``:

- Qdrant-backed tests skip themselves when Qdrant is unreachable. Chunks live in
  in-memory SQLite and embeddings are stubbed, so they need neither PostgreSQL
  nor OpenAI.
- The reranker wrapper is unit-tested with a stub model (no download).
- One opt-in test exercises the *real* cross-encoder; it is skipped unless
  ``RUN_RERANKER_MODEL_TESTS=1`` (it downloads model weights from the hub).

The headline test (``test_hybrid_recovers_exact_keyword_chunk_that_dense_misses``)
is also the RRF compatibility check against the running Qdrant server: it
exercises ``Prefetch`` + ``FusionQuery(RRF)`` end to end.
"""

import asyncio
import hashlib
import os
import random
import socket
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.models import Base, Chunk, Document, DocumentStatus
from app.services import indexing, vector_store
from app.services.embeddings.base import EmbeddingProvider
from app.services.retrieval import CrossEncoderReranker, RetrievalService


def _qdrant_reachable() -> bool:
    try:
        with socket.create_connection((settings.qdrant_host, settings.qdrant_port), timeout=1.0):
            return True
    except OSError:
        return False


def _sentence_transformers_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401

        return True
    except Exception:
        return False


requires_qdrant = pytest.mark.skipif(
    not _qdrant_reachable(),
    reason="Qdrant is not reachable (start infra/docker-compose.yml)",
)
requires_reranker_model = pytest.mark.skipif(
    not (os.getenv("RUN_RERANKER_MODEL_TESTS") and _sentence_transformers_available()),
    reason="set RUN_RERANKER_MODEL_TESTS=1 (with sentence-transformers) to run the real reranker",
)


# --- Test doubles --------------------------------------------------------


class ControlledDenseEmbedder(EmbeddingProvider):
    """Dense vectors hand-crafted per exact text so distances are controllable.

    Used to construct the case where a semantically-close *distractor* is the
    nearest dense neighbour, so pure dense search misses the chunk that actually
    holds the exact keyword (which only BM25 matches reliably).
    """

    def __init__(self, prefixes: dict[str, list[float]], dimension: int | None = None) -> None:
        self._prefixes = prefixes
        self._dimension = dimension or settings.embedding_dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        prefix = self._prefixes[text]  # KeyError surfaces a mis-wired test
        return prefix + [0.0] * (self._dimension - len(prefix))


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic random dense vectors: identical text -> identical vector."""

    def __init__(self, dimension: int | None = None) -> None:
        self._dimension = dimension or settings.embedding_dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(self._dimension)]


class FakeSparseEmbedder:
    """Deterministic BM25-style sparse vectors built from per-token hashes.

    A token only collides with itself, so a rare exact keyword in the query
    matches the chunk that contains it and nothing else — exactly the lexical
    signal BM25 provides in production.
    """

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


class StubReranker:
    """Reranks by a content->score map; stands in for the cross-encoder."""

    def __init__(self, scores_by_content: dict[str, float]) -> None:
        self._scores = scores_by_content

    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked = [
            {**candidate, "rerank_score": float(self._scores[candidate["content"]])}
            for candidate in candidates
        ]
        ranked.sort(key=lambda candidate: candidate["rerank_score"], reverse=True)
        return ranked


class _FakeCrossEncoderModel:
    """Minimal stand-in for ``sentence_transformers.CrossEncoder``."""

    def __init__(self, scores_by_content: dict[str, float]) -> None:
        self._scores = scores_by_content

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [self._scores[content] for _query, content in pairs]


# --- Fixtures / helpers --------------------------------------------------


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


async def _seed(
    factory: async_sessionmaker, contents: list[str]
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """Insert one document with one chunk per content string; return their ids."""
    document_id = uuid.uuid4()
    chunk_ids = [uuid.uuid4() for _ in contents]
    async with factory() as session:
        session.add(
            Document(
                id=document_id,
                filename="sample.md",
                content_type="text/markdown",
                status=DocumentStatus.indexed.value,
                uploaded_at=datetime.now(UTC),
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


def _unique_collection() -> str:
    return f"test_retrieval_{uuid.uuid4().hex[:12]}"


def _qdrant_test_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.qdrant_url, timeout=60)


# --- Tests: hybrid vs. dense --------------------------------------------


@requires_qdrant
def test_hybrid_recovers_exact_keyword_chunk_that_dense_misses() -> None:
    """Pure dense search misses an exact-keyword chunk; hybrid (RRF) recovers it.

    ``query`` is a rare error code. Dense vectors are arranged so the nearest
    neighbour is a semantically-similar *distractor* (general prose about
    database timeouts) rather than the chunk containing the literal code. BM25
    matches the literal code only in the target chunk, and RRF fusion pulls it
    to the top.
    """

    async def body() -> None:
        query = "ERR_DB_TIMEOUT_4711"
        target = (
            "The database driver raises ERR_DB_TIMEOUT_4711 when the connection pool is exhausted"
        )
        distractor = "Connections to the database can time out under heavy concurrent load"
        filler_a = "The user interface renders charts with a responsive grid layout"
        filler_b = "Authentication tokens expire after a configurable idle interval"
        contents = [target, distractor, filler_a, filler_b]

        # Dense geometry (first two dims; the rest are zero-padded): the query is
        # closest to the distractor, with the target only the second-nearest.
        prefixes = {
            query: [0.8, 0.6],
            target: [1.0, 0.0],  # cos(query) = 0.80
            distractor: [0.9, 0.4],  # cos(query) ~= 0.975  -> nearest
            filler_a: [-1.0, 0.0],  # cos(query) = -0.80
            filler_b: [0.0, -1.0],  # cos(query) = -0.60
        }
        dense = ControlledDenseEmbedder(prefixes)
        sparse = FakeSparseEmbedder()

        engine, factory = await _make_session_factory()
        client = _qdrant_test_client()
        collection = _unique_collection()
        document_id, chunk_ids = await _seed(factory, contents)
        target_id, distractor_id = str(chunk_ids[0]), str(chunk_ids[1])
        try:
            await indexing.index_document(
                document_id,
                embedding_provider=dense,
                sparse_embedder=sparse,
                collection_name=collection,
                session_factory=factory,
                client=client,
            )

            query_dense = dense.embed([query])[0]
            query_sparse = sparse.embed([query])[0]

            # Pure dense: the distractor wins, the exact-keyword chunk does not.
            dense_hits = await vector_store.search_dense(
                collection, query_dense, limit=len(contents), client=client
            )
            assert dense_hits[0].id == distractor_id
            assert dense_hits[0].id != target_id

            # Hybrid (dense + BM25, RRF): the exact-keyword chunk is recovered.
            hybrid_hits = await vector_store.search_hybrid(
                collection,
                dense_vector=query_dense,
                sparse_vector=query_sparse,
                limit=len(contents),
                prefetch_limit=len(contents),
                client=client,
            )
            assert hybrid_hits[0].id == target_id
        finally:
            await client.delete_collection(collection)
            await client.close()
            await engine.dispose()

    _run(body)


@requires_qdrant
def test_hybrid_filter_restricts_to_requested_documents() -> None:
    """A ``document_ids`` payload filter constrains hybrid search to one document."""

    async def body() -> None:
        dense = FakeEmbeddingProvider()
        sparse = FakeSparseEmbedder()
        engine, factory = await _make_session_factory()
        client = _qdrant_test_client()
        collection = _unique_collection()

        # Index two documents sharing the same query keyword.
        keep_id, _ = await _seed(factory, ["shared keyword alpha passage"])
        drop_id, _ = await _seed(factory, ["shared keyword beta passage"])
        try:
            for document_id in (keep_id, drop_id):
                await indexing.index_document(
                    document_id,
                    embedding_provider=dense,
                    sparse_embedder=sparse,
                    collection_name=collection,
                    session_factory=factory,
                    client=client,
                )

            service = RetrievalService(
                embedding_provider=dense,
                sparse_embedder=sparse,
                reranker=StubReranker(
                    {
                        "shared keyword alpha passage": 0.9,
                        "shared keyword beta passage": 0.8,
                    }
                ),
                collection_name=collection,
                client=client,
            )

            results = await service.retrieve(
                "shared keyword", top_k=5, filters={"document_ids": [str(keep_id)]}
            )

            assert results
            assert {result["document_id"] for result in results} == {str(keep_id)}
        finally:
            await client.delete_collection(collection)
            await client.close()
            await engine.dispose()

    _run(body)


@requires_qdrant
def test_retrieval_service_returns_reranked_topk_with_metadata() -> None:
    """End-to-end service wiring: hybrid search + rerank, top_k, full metadata."""

    async def body() -> None:
        contents = ["alpha one passage", "beta two passage", "gamma three passage"]
        # The reranker (stub) decides the final order, independent of fusion.
        rerank_scores = {
            "alpha one passage": 0.2,
            "beta two passage": 0.9,
            "gamma three passage": 0.5,
        }
        dense = FakeEmbeddingProvider()
        sparse = FakeSparseEmbedder()
        engine, factory = await _make_session_factory()
        client = _qdrant_test_client()
        collection = _unique_collection()
        document_id, chunk_ids = await _seed(factory, contents)
        try:
            await indexing.index_document(
                document_id,
                embedding_provider=dense,
                sparse_embedder=sparse,
                collection_name=collection,
                session_factory=factory,
                client=client,
            )

            service = RetrievalService(
                embedding_provider=dense,
                sparse_embedder=sparse,
                reranker=StubReranker(rerank_scores),
                collection_name=collection,
                client=client,
            )
            results = await service.retrieve("alpha one passage", top_k=2)

            # top_k honoured and ordered by the reranker's descending scores.
            assert len(results) == 2
            assert results[0]["content"] == "beta two passage"
            assert results[1]["content"] == "gamma three passage"
            assert results[0]["rerank_score"] >= results[1]["rerank_score"]

            top = results[0]
            assert top["chunk_id"] == str(chunk_ids[1])
            assert top["document_id"] == str(document_id)
            assert top["document_filename"] == "sample.md"
            assert top["page_number"] == 2
            assert top["section_path"] == "Chapter 1"
            assert isinstance(top["score"], float)  # RRF fusion score
            assert top["rerank_score"] == pytest.approx(0.9)
        finally:
            await client.delete_collection(collection)
            await client.close()
            await engine.dispose()

    _run(body)


# --- Tests: re-ranking ---------------------------------------------------


def test_reranker_reorders_candidates_and_preserves_fields() -> None:
    """The reranker sorts by model score, attaches rerank_score, keeps fusion score."""
    candidates = [
        {"chunk_id": "a", "content": "first by fusion", "score": 0.9},
        {"chunk_id": "b", "content": "second by fusion", "score": 0.5},
        {"chunk_id": "c", "content": "third by fusion", "score": 0.1},
    ]
    # The model considers "b" most relevant and "a" least — order must change.
    model = _FakeCrossEncoderModel(
        {"first by fusion": 0.1, "second by fusion": 0.95, "third by fusion": 0.4}
    )
    reranker = CrossEncoderReranker()
    reranker._model = model  # inject the stub, bypassing the lazy download

    reranked = reranker.rerank("a query", candidates)

    assert [item["chunk_id"] for item in reranked] == ["b", "c", "a"]
    assert [item["chunk_id"] for item in reranked] != [c["chunk_id"] for c in candidates]
    assert reranked[0]["rerank_score"] == pytest.approx(0.95)
    # First-stage fusion score is preserved alongside the new rerank score.
    assert reranked[0]["score"] == 0.5
    assert reranker.rerank("a query", []) == []


@requires_reranker_model
def test_real_cross_encoder_promotes_relevant_passage() -> None:
    """The real cross-encoder lifts the genuinely relevant passage to the top."""
    query = "What is the capital of France?"
    candidates = [
        {"chunk_id": "fruit", "content": "Bananas are a good source of potassium.", "score": 0.9},
        {"chunk_id": "paris", "content": "Paris is the capital city of France.", "score": 0.5},
        {"chunk_id": "wall", "content": "The Great Wall of China is very long.", "score": 0.1},
    ]
    reranker = CrossEncoderReranker()

    reranked = reranker.rerank(query, candidates)

    assert candidates[0]["chunk_id"] != "paris"  # not first before re-ranking
    assert reranked[0]["chunk_id"] == "paris"  # promoted after re-ranking
    assert "rerank_score" in reranked[0]
