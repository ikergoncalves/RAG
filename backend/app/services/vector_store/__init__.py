"""Vector-store package (Qdrant).

Re-exports the helpers from :mod:`qdrant_client` so callers can simply do
``from app.services import vector_store`` and use ``vector_store.ensure_collection(...)``.
"""

from app.services.vector_store.qdrant_client import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    Bm25SparseEmbedder,
    SparseEmbedder,
    count_points,
    ensure_collection,
    get_default_sparse_embedder,
    search_dense,
    upsert_points,
)

__all__ = [
    "DENSE_VECTOR_NAME",
    "SPARSE_VECTOR_NAME",
    "Bm25SparseEmbedder",
    "SparseEmbedder",
    "count_points",
    "ensure_collection",
    "get_default_sparse_embedder",
    "search_dense",
    "upsert_points",
]
