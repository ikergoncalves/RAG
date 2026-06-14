"""Embedding providers.

Exposes the :class:`EmbeddingProvider` interface and a lazily-constructed
process-wide default provider (OpenAI). The default is created on first use so
importing this package never requires an API key.
"""

from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.openai_provider import OpenAIEmbeddingProvider

_default_provider: EmbeddingProvider | None = None


def get_default_embedding_provider() -> EmbeddingProvider:
    """Return the shared default provider, constructing it on first use.

    Raises ``RuntimeError`` if no provider can be configured (e.g. a missing
    ``OPENAI_API_KEY``).
    """
    global _default_provider
    if _default_provider is None:
        _default_provider = OpenAIEmbeddingProvider()
    return _default_provider


__all__ = [
    "EmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "get_default_embedding_provider",
]
