"""Cohere-hosted re-ranking for retrieval candidates.

Re-ranking scores each ``(query, passage)`` pair jointly, which is far more
accurate than the bi-encoder similarity used during the first-stage hybrid
search — but also expensive, so it only runs over the handful of candidates that
survive fusion.

Unlike the previous local cross-encoder, scoring is delegated to Cohere's hosted
Rerank API (``settings.cohere_rerank_model``, default ``rerank-v3.5``). That
keeps the backend's memory footprint small — no ``torch`` / ``sentence-
transformers`` in the image — which is what makes it viable on hosts with little
RAM, such as the free tiers of several deploy platforms.

The Cohere client is created lazily on first use, so importing this module never
requires a configured API key. If the key is missing, or a call fails (rate
limit, timeout, network error), :meth:`CohereReranker.rerank` logs a warning and
returns the candidates in their original (fusion) order: a reranker outage
degrades retrieval quality but never takes the application down.
"""

import logging
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    import cohere

logger = logging.getLogger(__name__)

# Payload key holding the passage text scored against the query.
_CONTENT_KEY = "content"
# Field added to each candidate with its rerank relevance score.
_RERANK_SCORE_KEY = "rerank_score"


class CohereReranker:
    """Re-orders retrieval candidates by Cohere Rerank relevance.

    Mirrors the public interface of the previous ``CrossEncoderReranker``:
    ``rerank(query, candidates) -> candidates`` with a ``rerank_score`` added to
    each, sorted by descending relevance — so it is a drop-in replacement.
    """

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or settings.cohere_api_key
        self._model = model or settings.cohere_rerank_model
        self._client: cohere.ClientV2 | None = None

    def _ensure_client(self) -> "cohere.ClientV2 | None":
        """Return the lazily-built Cohere client, or ``None`` if no key is set."""
        if self._client is None:
            if not self._api_key:
                return None
            import cohere

            logger.info("Initializing Cohere rerank client (model %r)", self._model)
            self._client = cohere.ClientV2(api_key=self._api_key)
        return self._client

    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return ``candidates`` sorted by descending relevance to ``query``.

        Each returned candidate is a shallow copy of the input with a
        ``rerank_score`` (float) added; the original fields (including the
        first-stage fusion ``score``) are preserved.

        Any failure — missing API key, rate limit, timeout, network error —
        is swallowed: the method logs a warning and falls back to the original
        candidate order (see :meth:`_fallback`), so a reranker problem never
        propagates an exception to the caller.
        """
        if not candidates:
            return []

        client = self._ensure_client()
        if client is None:
            logger.warning("COHERE_API_KEY is not configured; returning candidates unranked")
            return self._fallback(candidates)

        documents = [candidate[_CONTENT_KEY] for candidate in candidates]
        try:
            response = client.rerank(
                model=self._model,
                query=query,
                documents=documents,
                top_n=len(documents),
            )
        except Exception as exc:  # pragma: no cover - API/network dependent
            # Rate limits, timeouts and transient network errors must degrade
            # gracefully rather than fail the request.
            logger.warning("Cohere rerank failed (%s); returning candidates unranked", exc)
            return self._fallback(candidates)

        ranked = [
            {**candidates[result.index], _RERANK_SCORE_KEY: float(result.relevance_score)}
            for result in response.results
        ]
        # The API already returns results sorted by relevance, but sort defensively
        # so the contract holds regardless of response ordering.
        ranked.sort(key=lambda candidate: candidate[_RERANK_SCORE_KEY], reverse=True)
        return ranked

    @staticmethod
    def _fallback(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return candidates in their original order, each given a ``rerank_score``.

        Keeps the result shape identical to a successful rerank (every candidate
        carries a ``rerank_score``) so downstream consumers need no special case;
        the first-stage fusion ``score`` stands in as the relevance value.
        """
        return [
            {**candidate, _RERANK_SCORE_KEY: float(candidate.get("score", 0.0))}
            for candidate in candidates
        ]


_default_reranker: CohereReranker | None = None


def get_default_reranker() -> CohereReranker:
    """Return the shared Cohere reranker (client built on first use)."""
    global _default_reranker
    if _default_reranker is None:
        _default_reranker = CohereReranker()
    return _default_reranker
