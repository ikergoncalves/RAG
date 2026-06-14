"""Qdrant vector-store helpers: collection management, sparse (BM25) vectors,
upsert and search.

The collection stores two named vectors per point so the retrieval phase can do
hybrid search:

- ``"dense"``  — 1536-dim cosine-distance vector from the embedding provider.
- ``"sparse"`` — BM25 sparse vector produced by FastEmbed. The collection uses
  the IDF modifier so Qdrant applies the inverse-document-frequency term of BM25
  at query time (FastEmbed supplies the term frequencies).

A single :class:`AsyncQdrantClient` is shared process-wide (reused from
``app.db.qdrant``); helpers accept an optional ``client`` override so tests can
inject a client bound to their own event loop.
"""

import logging
from typing import TYPE_CHECKING, Protocol

from qdrant_client import AsyncQdrantClient, models

from app.core.config import settings
from app.db.qdrant import qdrant_client

if TYPE_CHECKING:
    from fastembed import SparseTextEmbedding

logger = logging.getLogger(__name__)

# Named-vector keys; shared with the indexing job and (later) retrieval.
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


class SparseEmbedder(Protocol):
    """Anything that turns texts into BM25-style sparse vectors."""

    def embed(self, texts: list[str]) -> list[models.SparseVector]: ...


def _client(client: AsyncQdrantClient | None) -> AsyncQdrantClient:
    return client or qdrant_client


async def ensure_collection(
    collection_name: str | None = None,
    *,
    dimension: int | None = None,
    client: AsyncQdrantClient | None = None,
) -> str:
    """Create the hybrid collection if it does not already exist.

    Returns the resolved collection name. Idempotent: an existing collection is
    left untouched.
    """
    name = collection_name or settings.qdrant_collection
    dim = dimension or settings.embedding_dimensions
    qc = _client(client)

    if await qc.collection_exists(name):
        return name

    await qc.create_collection(
        collection_name=name,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(size=dim, distance=models.Distance.COSINE),
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: models.SparseVectorParams(
                modifier=models.Modifier.IDF,
            ),
        },
    )
    logger.info("Created Qdrant collection %r (dense dim=%d + sparse BM25)", name, dim)
    return name


async def upsert_points(
    collection_name: str,
    points: list[models.PointStruct],
    *,
    client: AsyncQdrantClient | None = None,
    wait: bool = True,
) -> None:
    """Upsert points. Reusing a point's id overwrites it (no duplicates)."""
    if not points:
        return
    await _client(client).upsert(collection_name=collection_name, points=points, wait=wait)


async def count_points(collection_name: str, *, client: AsyncQdrantClient | None = None) -> int:
    """Exact number of points currently stored in the collection."""
    result = await _client(client).count(collection_name=collection_name, exact=True)
    return result.count


async def search_dense(
    collection_name: str,
    query_vector: list[float],
    *,
    limit: int = 5,
    client: AsyncQdrantClient | None = None,
    with_payload: bool = True,
) -> list[models.ScoredPoint]:
    """Nearest-neighbour search over the dense vector (debug/test helper)."""
    response = await _client(client).query_points(
        collection_name=collection_name,
        query=query_vector,
        using=DENSE_VECTOR_NAME,
        limit=limit,
        with_payload=with_payload,
    )
    return response.points


class Bm25SparseEmbedder:
    """Produces BM25 sparse vectors via FastEmbed.

    The FastEmbed model is loaded lazily on first use (it downloads/caches model
    files), so importing this module never triggers a download.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or settings.sparse_embedding_model
        self._model: SparseTextEmbedding | None = None

    def _ensure_model(self) -> "SparseTextEmbedding":
        if self._model is None:
            from fastembed import SparseTextEmbedding

            logger.info("Loading FastEmbed sparse model %r", self._model_name)
            self._model = SparseTextEmbedding(model_name=self._model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[models.SparseVector]:
        if not texts:
            return []
        model = self._ensure_model()
        return [
            models.SparseVector(
                indices=embedding.indices.tolist(),
                values=embedding.values.tolist(),
            )
            for embedding in model.embed(texts)
        ]


_default_sparse_embedder: Bm25SparseEmbedder | None = None


def get_default_sparse_embedder() -> Bm25SparseEmbedder:
    """Return the shared BM25 sparse embedder (model loaded on first use)."""
    global _default_sparse_embedder
    if _default_sparse_embedder is None:
        _default_sparse_embedder = Bm25SparseEmbedder()
    return _default_sparse_embedder
