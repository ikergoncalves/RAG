"""Chat orchestration: retrieve, generate a cited answer, persist, stream.

``ChatService.ask`` ties the retrieval and generation stages together and
persists the conversation:

1. Create a :class:`Conversation` (when none is supplied) and persist the user's
   question as a :class:`Message`.
2. Retrieve the relevant chunks for the question.
3. If nothing is retrieved, yield the fixed "I don't have enough information"
   answer **without calling the LLM** (zero token cost), persist it, and stop.
4. Otherwise stream the answer (yielding ``{"type": "delta", "text": ...}`` per
   token), then extract citations and enrich each with the source chunk's
   document/page/section metadata.
5. Persist the assistant message (full answer + serialized citations) and yield a
   final ``{"type": "citations", "conversation_id": ..., "citations": [...]}``.

Retrieval service, LLM provider and the SQLAlchemy session factory are all
injectable so the flow can be unit-tested against in-memory SQLite with a fake
provider — no API keys or Qdrant required.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import AsyncSessionLocal
from app.models.conversation import Conversation, Message
from app.services.llm import INSUFFICIENT_CONTEXT_MESSAGE, LLMProvider, get_default_llm_provider
from app.services.retrieval import RetrievalService, get_default_retrieval_service

_USER_ROLE = "user"
_ASSISTANT_ROLE = "assistant"


class ChatService:
    """Retrieve-then-generate chat with persisted, cited assistant answers."""

    def __init__(
        self,
        *,
        llm_provider: LLMProvider | None = None,
        retrieval_service: RetrievalService | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._llm_provider = llm_provider
        self._retrieval_service = retrieval_service
        self._session_factory = session_factory

    async def ask(
        self, question: str, conversation_id: uuid.UUID | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Answer ``question``, streaming text deltas then a citations event."""
        provider = self._llm_provider or get_default_llm_provider()
        retrieval = self._retrieval_service or get_default_retrieval_service()
        factory = self._session_factory or AsyncSessionLocal

        # 1. Resolve/create the conversation and persist the user's question.
        conversation_id = await self._persist_user_message(factory, conversation_id, question)

        # 2. Retrieve the supporting chunks.
        context_chunks = await retrieval.retrieve(question)

        # 3. No context -> fixed refusal, no LLM call (zero token cost).
        if not context_chunks:
            await self._persist_assistant_message(
                factory, conversation_id, INSUFFICIENT_CONTEXT_MESSAGE, []
            )
            yield {"type": "delta", "text": INSUFFICIENT_CONTEXT_MESSAGE}
            yield {
                "type": "citations",
                "conversation_id": str(conversation_id),
                "citations": [],
            }
            return

        # 4. Stream the cited answer, accumulating the full text.
        parts: list[str] = []
        async for delta in provider.generate_answer(question, context_chunks):
            parts.append(delta)
            yield {"type": "delta", "text": delta}
        answer = "".join(parts)

        # 5. Extract citations and enrich them with source metadata.
        raw_citations = await provider.extract_citations(question, answer, context_chunks)
        citations = _enrich_citations(raw_citations, context_chunks)

        # 6. Persist the assistant message (answer + serialized citations).
        await self._persist_assistant_message(factory, conversation_id, answer, citations)

        # 7. Final citations event.
        yield {
            "type": "citations",
            "conversation_id": str(conversation_id),
            "citations": citations,
        }

    async def _persist_user_message(
        self,
        factory: async_sessionmaker[AsyncSession],
        conversation_id: uuid.UUID | None,
        question: str,
    ) -> uuid.UUID:
        async with factory() as session:
            if conversation_id is None:
                conversation = Conversation()
                session.add(conversation)
                await session.flush()
                conversation_id = conversation.id
            session.add(
                Message(conversation_id=conversation_id, role=_USER_ROLE, content=question)
            )
            await session.commit()
        return conversation_id

    async def _persist_assistant_message(
        self,
        factory: async_sessionmaker[AsyncSession],
        conversation_id: uuid.UUID,
        content: str,
        citations: list[dict[str, Any]],
    ) -> None:
        async with factory() as session:
            session.add(
                Message(
                    conversation_id=conversation_id,
                    role=_ASSISTANT_ROLE,
                    content=content,
                    citations=citations,
                )
            )
            await session.commit()


def _enrich_citations(
    raw_citations: list[dict[str, Any]], context_chunks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach document/page/section metadata from the cited source chunk.

    Citations whose ``chunk_id`` is missing from the context are skipped (the
    provider already drops unknown ids; this is a defensive second guard).
    """
    by_chunk_id = {str(chunk["chunk_id"]): chunk for chunk in context_chunks}
    enriched: list[dict[str, Any]] = []
    for citation in raw_citations:
        chunk = by_chunk_id.get(str(citation.get("chunk_id")))
        if chunk is None:
            continue
        enriched.append(
            {
                "number": citation.get("number"),
                "chunk_id": citation.get("chunk_id"),
                "quote": citation.get("quote"),
                "document_id": chunk.get("document_id"),
                "document_name": chunk.get("document_filename"),
                "page": chunk.get("page_number"),
                "section": chunk.get("section_path"),
            }
        )
    return enriched
