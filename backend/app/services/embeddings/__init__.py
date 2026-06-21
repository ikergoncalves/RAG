"""Embedding providers.

Exposes the :class:`EmbeddingProvider` interface and a lazily-constructed
process-wide default provider (OpenAI). The default provider *and* the
``OpenAIEmbeddingProvider`` symbol are resolved lazily, so importing this
package never imports the OpenAI SDK. That keeps the SDK off the application's
startup/import path (it loads only on first embedding use), which matters for
the memory footprint on RAM-limited hosts.
"""

from typing import TYPE_CHECKING

from app.services.embeddings.base import EmbeddingProvider

if TYPE_CHECKING:
    from app.services.embeddings.openai_provider import OpenAIEmbeddingProvider

_default_provider: EmbeddingProvider | None = None


def get_default_embedding_provider() -> EmbeddingProvider:
    """Return the shared default provider, constructing it on first use.

    Raises ``RuntimeError`` if no provider can be configured (e.g. a missing
    ``OPENAI_API_KEY``).
    """
    global _default_provider
    if _default_provider is None:
        # Imported lazily so importing this package never imports the SDK.
        from app.services.embeddings.openai_provider import OpenAIEmbeddingProvider

        _default_provider = OpenAIEmbeddingProvider()
    return _default_provider


def __getattr__(name: str) -> object:
    """Resolve ``OpenAIEmbeddingProvider`` lazily (PEP 562).

    Lets ``from app.services.embeddings import OpenAIEmbeddingProvider`` keep
    working without importing the OpenAI SDK at package-import time.
    """
    if name == "OpenAIEmbeddingProvider":
        from app.services.embeddings.openai_provider import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "get_default_embedding_provider",
]
