"""LLM provider interface for cited answer generation.

The rest of the codebase depends only on this abstraction so the generation
backend stays swappable (per the project conventions, no Anthropic-specific code
leaks outside ``anthropic_provider``). A provider does two things:

- :meth:`LLMProvider.generate_answer` streams a plain-text answer grounded only
  in the numbered context chunks, inserting ``[n]`` markers where each source is
  used.
- :meth:`LLMProvider.extract_citations` turns that already-generated answer into
  a list of ``{number, chunk_id, quote}`` objects whose ``quote`` is a verbatim
  excerpt of the referenced chunk's ``content``.

``context_chunks`` are the dicts returned by ``RetrievalService.retrieve`` and
must already be in the order the caller numbered them (``[1]`` is the first
element, ``[2]`` the second, ...).
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

# Returned verbatim when the retrieved context does not cover the question, so
# the model never invents an answer or citations. Shared by the provider (it is
# the instructed refusal string) and the ChatService zero-cost short-circuit.
INSUFFICIENT_CONTEXT_MESSAGE = "I don't have enough information to answer this question."


class LLMProvider(ABC):
    """Abstract provider for streaming generation and citation extraction."""

    @abstractmethod
    def generate_answer(
        self, question: str, context_chunks: list[dict[str, Any]]
    ) -> AsyncIterator[str]:
        """Stream the answer to ``question`` grounded in ``context_chunks``.

        Yields plain-text deltas. The answer must rely solely on the numbered
        passages ``[1]..[n]`` (one per ``context_chunks`` element, in order) and
        insert ``[n]`` markers at the points where each source is used. When the
        context does not cover the question, the whole answer is exactly
        :data:`INSUFFICIENT_CONTEXT_MESSAGE` with no citation markers.
        """
        raise NotImplementedError

    @abstractmethod
    async def extract_citations(
        self, question: str, answer: str, context_chunks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Return the citations backing an already-generated ``answer``.

        Each item is ``{"number": int, "chunk_id": str, "quote": str}`` where
        ``quote`` is a literal (verbatim) substring of the referenced chunk's
        ``content``. Implementations must drop any citation whose ``chunk_id`` is
        not present in ``context_chunks``.
        """
        raise NotImplementedError
