"""Retrieval package: hybrid (dense + BM25) search with Cohere re-ranking.

Re-exports the service and reranker so callers can do
``from app.services.retrieval import RetrievalService``.
"""

from app.services.retrieval.cohere_reranker import CohereReranker, get_default_reranker
from app.services.retrieval.service import (
    RetrievalOutcome,
    RetrievalService,
    get_default_retrieval_service,
)

__all__ = [
    "CohereReranker",
    "RetrievalOutcome",
    "RetrievalService",
    "get_default_reranker",
    "get_default_retrieval_service",
]
