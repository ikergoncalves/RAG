"""Retrieval package: hybrid (dense + BM25) search with cross-encoder re-ranking.

Re-exports the service and reranker so callers can do
``from app.services.retrieval import RetrievalService``.
"""

from app.services.retrieval.cross_encoder import CrossEncoderReranker, get_default_reranker
from app.services.retrieval.service import (
    RetrievalOutcome,
    RetrievalService,
    get_default_retrieval_service,
)

__all__ = [
    "CrossEncoderReranker",
    "RetrievalOutcome",
    "RetrievalService",
    "get_default_reranker",
    "get_default_retrieval_service",
]
