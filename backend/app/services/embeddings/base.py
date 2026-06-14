"""Embedding provider interface.

The rest of the codebase depends only on this abstraction so the embedding
backend stays swappable (per the project conventions, no OpenAI-specific code
leaks outside ``openai_provider``). A provider turns text into dense float
vectors of a fixed dimensionality.
"""

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstract dense-embedding provider."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one dense vector per input text, in the same order.

        Implementations are expected to be synchronous and may block on network
        I/O; callers running on the event loop should offload them to a worker
        thread (e.g. ``asyncio.to_thread``).
        """
        raise NotImplementedError
