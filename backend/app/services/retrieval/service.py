"""Hybrid retrieval: dense + BM25 fusion in Qdrant, then cross-encoder re-ranking.

``RetrievalService.retrieve`` runs the two-stage retrieval pipeline:

1. Embed the query densely (:class:`EmbeddingProvider`) and as a BM25 sparse
   vector (FastEmbed).
2. Run a hybrid Qdrant search — a dense and a sparse prefetch fused with RRF —
   returning ~``retrieval_candidates`` candidates, optionally filtered by
   ``document_id``.
3. Re-rank those candidates with a cross-encoder and return the top ``top_k``.

Each result carries the metadata needed for cited generation and the source
viewer: ``chunk_id``, ``document_id``, ``document_filename``, ``page_number``,
``section_path``, ``content``, the fusion ``score`` and the ``rerank_score``.

Providers (embedding, sparse, reranker), the collection name and the Qdrant
client are all injectable so tests can supply doubles bound to their own event
loop and collection.
"""

import asyncio
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.core.config import settings
from app.services import vector_store
from app.services.cache import CacheService, get_default_cache
from app.services.embeddings import EmbeddingProvider, get_default_embedding_provider
from app.services.retrieval.cross_encoder import CrossEncoderReranker, get_default_reranker

logger = logging.getLogger(__name__)


@dataclass
class RetrievalOutcome:
    """Result of a retrieval run with the metrics needed for observability.

    ``candidates`` are the fused hybrid-search hits *before* re-ranking, and
    ``reranked`` are the final ``top_k`` after the cross-encoder. The two stage
    latencies and the embedding cache-hit flag let the caller log, trace and
    cost each request without re-deriving them.
    """

    candidates: list[dict[str, Any]]
    reranked: list[dict[str, Any]]
    retrieval_ms: float
    rerank_ms: float
    cache_hit_embedding: bool


class RetrievalService:
    """Hybrid (dense + BM25) retrieval with cross-encoder re-ranking."""

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        sparse_embedder: vector_store.SparseEmbedder | None = None,
        reranker: CrossEncoderReranker | None = None,
        collection_name: str | None = None,
        client: AsyncQdrantClient | None = None,
        cache_service: CacheService | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._sparse_embedder = sparse_embedder
        self._reranker = reranker
        self._collection_name = collection_name
        self._client = client
        self._cache_service = cache_service

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the ``top_k`` most relevant chunks for ``query``.

        ``filters`` may contain ``document_ids`` (a list of document-id strings)
        to restrict retrieval to those documents.
        """
        outcome = await self.retrieve_with_metrics(query, top_k=top_k, filters=filters)
        return outcome.reranked

    async def retrieve_with_metrics(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> RetrievalOutcome:
        """Run retrieval and return the chunks plus per-stage metrics.

        Splits the pipeline into a timed first stage (query embedding — served
        from the Redis cache when possible — plus hybrid Qdrant search) and a
        timed re-ranking stage, exposing both candidate sets so callers can log
        retrieved vs. re-ranked chunk ids.
        """
        provider = self._embedding_provider or get_default_embedding_provider()
        sparse = self._sparse_embedder or vector_store.get_default_sparse_embedder()
        reranker = self._reranker or get_default_reranker()
        collection = self._collection_name or settings.qdrant_collection
        cache = self._cache_service

        retrieval_start = perf_counter()

        # Nothing is indexed yet -> nothing to retrieve (avoids a 500 on an
        # empty system); ensure_collection is idempotent.
        await vector_store.ensure_collection(collection, client=self._client)

        # Dense query embedding: reuse the cached vector when available so a
        # repeated query never pays the embedding provider again.
        cache_hit_embedding = False
        dense_vector: list[float] | None = None
        if cache is not None:
            cached = await cache.get_query_embedding(query)
            if cached is not None:
                dense_vector = cached
                cache_hit_embedding = True
        if dense_vector is None:
            # Both embedders block (network / CPU); run them off the event loop.
            dense_vector = (await asyncio.to_thread(provider.embed, [query]))[0]
            if cache is not None:
                await cache.set_query_embedding(query, dense_vector)

        sparse_vector = (await asyncio.to_thread(sparse.embed, [query]))[0]

        points = await vector_store.search_hybrid(
            collection,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            limit=settings.retrieval_candidates,
            prefetch_limit=settings.retrieval_prefetch_limit,
            query_filter=_build_filter(filters),
            client=self._client,
        )
        candidates = [_point_to_candidate(point) for point in points]
        retrieval_ms = (perf_counter() - retrieval_start) * 1000

        rerank_start = perf_counter()
        reranked = await asyncio.to_thread(reranker.rerank, query, candidates)
        rerank_ms = (perf_counter() - rerank_start) * 1000

        return RetrievalOutcome(
            candidates=candidates,
            reranked=reranked[:top_k],
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            cache_hit_embedding=cache_hit_embedding,
        )


def _build_filter(filters: dict[str, Any] | None) -> models.Filter | None:
    """Translate the public ``filters`` dict into a Qdrant payload filter."""
    if not filters:
        return None
    document_ids = filters.get("document_ids")
    if not document_ids:
        return None
    return models.Filter(
        must=[
            models.FieldCondition(
                key="document_id",
                match=models.MatchAny(any=[str(value) for value in document_ids]),
            )
        ]
    )


def _point_to_candidate(point: models.ScoredPoint) -> dict[str, Any]:
    """Flatten a scored Qdrant point into a retrieval candidate dict."""
    payload = point.payload or {}
    return {
        "chunk_id": str(point.id),
        "document_id": payload.get("document_id"),
        "document_filename": payload.get("document_filename"),
        "page_number": payload.get("page_number"),
        "section_path": payload.get("section_path"),
        "content": payload.get("content", ""),
        # First-stage Reciprocal Rank Fusion score from the hybrid search.
        "score": point.score,
    }


_default_service: RetrievalService | None = None


def get_default_retrieval_service() -> RetrievalService:
    """Return the shared retrieval service (reuses the lazily-loaded reranker)."""
    global _default_service
    if _default_service is None:
        # Wire the query-embedding cache into the process-wide default service.
        _default_service = RetrievalService(cache_service=get_default_cache())
    return _default_service
