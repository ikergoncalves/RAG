"""OpenAI implementation of :class:`EmbeddingProvider`.

Uses the ``text-embedding-3-small`` model (1536 dimensions by default). Inputs
are sent in batches, and transient failures (rate limits, timeouts, upstream
5xx) are retried with exponential backoff.
"""

import logging
import time
from typing import TYPE_CHECKING

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from app.core.config import settings
from app.services.embeddings.base import EmbeddingProvider

if TYPE_CHECKING:
    from openai import OpenAI as OpenAIClient

logger = logging.getLogger(__name__)

# Errors worth retrying: transient server/network conditions, not client errors
# such as an invalid request or bad API key.
_RETRYABLE_ERRORS = (
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    InternalServerError,
)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Dense embeddings backed by the OpenAI Embeddings API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        batch_size: int | None = None,
        max_retries: int | None = None,
        initial_backoff: float = 1.0,
        max_backoff: float = 30.0,
        client: "OpenAIClient | None" = None,
    ) -> None:
        api_key = api_key or settings.openai_api_key
        if not api_key and client is None:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured; cannot create OpenAIEmbeddingProvider"
            )
        self._model = model or settings.embedding_model
        self._dimensions = dimensions or settings.embedding_dimensions
        self._batch_size = batch_size or settings.embedding_batch_size
        self._max_retries = (
            max_retries if max_retries is not None else settings.embedding_max_retries
        )
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        # Disable the SDK's own retries; backoff is handled explicitly below.
        self._client = client or OpenAI(api_key=api_key, max_retries=0)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        backoff = self._initial_backoff
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.embeddings.create(
                    model=self._model,
                    input=batch,
                    dimensions=self._dimensions,
                )
                # The API preserves input order, but sort defensively on ``index``.
                ordered = sorted(response.data, key=lambda item: item.index)
                return [item.embedding for item in ordered]
            except _RETRYABLE_ERRORS as exc:
                if attempt >= self._max_retries:
                    raise
                logger.warning(
                    "OpenAI embeddings transient error (%s); retry %d/%d in %.1fs",
                    type(exc).__name__,
                    attempt + 1,
                    self._max_retries,
                    backoff,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff)
        # Unreachable: the loop either returns or re-raises on the last attempt.
        raise RuntimeError("OpenAI embeddings retries exhausted")
