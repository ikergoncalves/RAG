"""Cross-encoder re-ranking for retrieval candidates.

A cross-encoder scores a (query, passage) pair jointly, which is far more
accurate than the bi-encoder similarity used during the first-stage hybrid
search — but also far more expensive, so it only runs over the handful of
candidates that survive fusion. The model is loaded lazily on first use (it
downloads/caches weights from the Hugging Face hub), so importing this module
never triggers a download.

The default model (``settings.reranker_model``) is a small, CPU-friendly
cross-encoder; see ``app/core/config.py`` for why and how to swap it.
"""

import logging
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

# Payload key holding the passage text scored against the query.
_CONTENT_KEY = "content"
# Field added to each candidate with its cross-encoder relevance score.
_RERANK_SCORE_KEY = "rerank_score"


class CrossEncoderReranker:
    """Re-orders retrieval candidates by cross-encoder relevance."""

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or settings.reranker_model
        self._model: CrossEncoder | None = None

    def _ensure_model(self) -> "CrossEncoder":
        if self._model is None:
            from sentence_transformers import CrossEncoder

            logger.info("Loading cross-encoder reranker %r", self._model_name)
            self._model = CrossEncoder(self._model_name)
        return self._model

    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return ``candidates`` sorted by descending relevance to ``query``.

        Each returned candidate is a shallow copy of the input with a
        ``rerank_score`` (float) added; the original fields (including the
        first-stage fusion ``score``) are preserved.
        """
        if not candidates:
            return []

        model = self._ensure_model()
        pairs = [(query, candidate[_CONTENT_KEY]) for candidate in candidates]
        scores = model.predict(pairs)

        ranked = [
            {**candidate, _RERANK_SCORE_KEY: float(score)}
            for candidate, score in zip(candidates, scores, strict=True)
        ]
        ranked.sort(key=lambda candidate: candidate[_RERANK_SCORE_KEY], reverse=True)
        return ranked


_default_reranker: CrossEncoderReranker | None = None


def get_default_reranker() -> CrossEncoderReranker:
    """Return the shared cross-encoder reranker (model loaded on first use)."""
    global _default_reranker
    if _default_reranker is None:
        _default_reranker = CrossEncoderReranker()
    return _default_reranker
