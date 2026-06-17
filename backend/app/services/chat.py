"""Chat orchestration: retrieve, generate a cited answer, persist, stream.

``ChatService.ask`` ties the retrieval and generation stages together and
persists the conversation:

1. Create a :class:`Conversation` (when none is supplied) and persist the user's
   question as a :class:`Message`.
2. Serve a **cached response** for an identical (normalized) question without
   touching retrieval or the LLM, replaying it as a real-looking stream.
3. Otherwise retrieve the relevant chunks for the question.
4. If nothing is retrieved, yield the fixed "I don't have enough information"
   answer **without calling the LLM** (zero token cost), persist it, and stop.
5. Otherwise stream the answer (yielding ``{"type": "delta", "text": ...}`` per
   token), extract citations, enrich them with source metadata, and cache the
   full response for next time.
6. Persist the assistant message and yield a final ``{"type": "citations", ...}``.

Each request emits one structured log line (query, retrieved/re-ranked chunk
ids, per-stage latency, token usage, estimated cost, cache-hit flags), records
Prometheus metrics, and is traced in Langfuse with spans per stage. Retrieval
service, LLM provider, the session factory, the cache and the observability
service are all injectable so the flow can be unit-tested against in-memory
SQLite with fakes — no API keys, Qdrant or Redis required.
"""

import uuid
from collections.abc import AsyncIterator, Iterator
from time import perf_counter
from typing import Any

import tiktoken
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import add_cost, observe_stage, record_cache
from app.db.session import AsyncSessionLocal
from app.models.conversation import Conversation, Message
from app.services.cache import CacheService
from app.services.llm import INSUFFICIENT_CONTEXT_MESSAGE, LLMProvider, get_default_llm_provider
from app.services.observability import ObservabilityService, get_observability
from app.services.retrieval import (
    RetrievalOutcome,
    RetrievalService,
    get_default_retrieval_service,
)

logger = get_logger(__name__)

_USER_ROLE = "user"
_ASSISTANT_ROLE = "assistant"

# Slice size (characters) used to replay a cached answer as several deltas so the
# frontend cannot tell a cache hit from a live stream.
_REPLAY_CHUNK_CHARS = 120

_encoder: "tiktoken.Encoding | None" = None


class ChatService:
    """Retrieve-then-generate chat with persisted, cited assistant answers."""

    def __init__(
        self,
        *,
        llm_provider: LLMProvider | None = None,
        retrieval_service: RetrievalService | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        cache_service: CacheService | None = None,
        observability: ObservabilityService | None = None,
    ) -> None:
        self._llm_provider = llm_provider
        self._retrieval_service = retrieval_service
        self._session_factory = session_factory
        self._cache_service = cache_service
        self._observability = observability

    async def ask(
        self, question: str, conversation_id: uuid.UUID | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Answer ``question``, streaming text deltas then a citations event."""
        provider = self._llm_provider or get_default_llm_provider()
        retrieval = self._retrieval_service or get_default_retrieval_service()
        factory = self._session_factory or AsyncSessionLocal
        cache = self._cache_service
        observability = self._observability or get_observability()

        total_start = perf_counter()
        trace = observability.start_trace(name="chat", input={"question": question})
        try:
            # 1. Response cache: an identical question is answered without
            #    retrieval or the LLM.
            cached_response = await cache.get_response(question) if cache is not None else None

            # 2. Resolve/create the conversation and persist the user's question.
            conversation_id = await self._persist_user_message(factory, conversation_id, question)

            if cached_response is not None:
                async for item in self._serve_cached_response(
                    factory, conversation_id, question, cached_response, total_start
                ):
                    yield item
                return
            if cache is not None:
                record_cache("response", False)

            # 3. Retrieve the supporting chunks (with per-stage metrics).
            outcome = await self._retrieve(retrieval, question, trace)
            context_chunks = outcome.reranked
            retrieved_ids = [str(chunk["chunk_id"]) for chunk in outcome.candidates]
            reranked_ids = [str(chunk["chunk_id"]) for chunk in context_chunks]
            if cache is not None:
                record_cache("embedding", outcome.cache_hit_embedding)
            embedding_tokens = 0 if outcome.cache_hit_embedding else _count_tokens(question)

            # 4. No context -> fixed refusal, no LLM call (zero token cost).
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
                cost = _estimate_cost(0, 0, embedding_tokens)
                add_cost(cost)
                total_ms = (perf_counter() - total_start) * 1000
                observe_stage("total", total_ms / 1000)
                logger.info(
                    "chat.request",
                    query=question,
                    retrieved_chunk_ids=retrieved_ids,
                    reranked_chunk_ids=[],
                    retrieval_ms=round(outcome.retrieval_ms, 2),
                    rerank_ms=round(outcome.rerank_ms, 2),
                    generation_ms=0.0,
                    total_ms=round(total_ms, 2),
                    prompt_tokens=0,
                    completion_tokens=0,
                    estimated_cost_usd=round(cost, 6),
                    cache_hit_embedding=outcome.cache_hit_embedding,
                    cache_hit_response=False,
                )
                trace.update(output={"answer": INSUFFICIENT_CONTEXT_MESSAGE, "citations": 0})
                return

            # 5. Stream the cited answer, capturing token usage.
            usage: dict[str, int] = {}
            generation_span = trace.span(
                name="generation",
                input={"question": question, "num_context": len(context_chunks)},
            )
            generation_start = perf_counter()
            parts: list[str] = []
            async for delta in provider.generate_answer(question, context_chunks, usage_sink=usage):
                parts.append(delta)
                yield {"type": "delta", "text": delta}
            answer = "".join(parts)
            generation_ms = (perf_counter() - generation_start) * 1000
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            observe_stage("generation", generation_ms / 1000)
            generation_span.end(
                output={"answer_chars": len(answer)},
                metadata={
                    "generation_ms": round(generation_ms, 2),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
            )

            # 6. Extract citations and enrich them with source metadata.
            raw_citations = await provider.extract_citations(question, answer, context_chunks)
            citations = _enrich_citations(raw_citations, context_chunks)

            # 7. Persist the assistant message and cache the full response.
            await self._persist_assistant_message(factory, conversation_id, answer, citations)
            if cache is not None:
                await cache.set_response(question, {"answer": answer, "citations": citations})

            # 8. Final citations event.
            yield {
                "type": "citations",
                "conversation_id": str(conversation_id),
                "citations": citations,
            }

            cost = _estimate_cost(prompt_tokens, completion_tokens, embedding_tokens)
            add_cost(cost)
            total_ms = (perf_counter() - total_start) * 1000
            observe_stage("total", total_ms / 1000)
            logger.info(
                "chat.request",
                query=question,
                retrieved_chunk_ids=retrieved_ids,
                reranked_chunk_ids=reranked_ids,
                retrieval_ms=round(outcome.retrieval_ms, 2),
                rerank_ms=round(outcome.rerank_ms, 2),
                generation_ms=round(generation_ms, 2),
                total_ms=round(total_ms, 2),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                estimated_cost_usd=round(cost, 6),
                cache_hit_embedding=outcome.cache_hit_embedding,
                cache_hit_response=False,
            )
            trace.update(
                output={"answer_chars": len(answer), "citations": len(citations)},
                metadata={
                    "total_ms": round(total_ms, 2),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "estimated_cost_usd": round(cost, 6),
                },
            )
        finally:
            observability.flush()

    async def _retrieve(self, retrieval: Any, question: str, trace: Any) -> RetrievalOutcome:
        """Run retrieval (with metrics) and record the retrieval/rerank spans.

        Falls back to the plain ``retrieve`` interface for retrieval doubles that
        do not implement ``retrieve_with_metrics``.
        """
        if hasattr(retrieval, "retrieve_with_metrics"):
            outcome = await retrieval.retrieve_with_metrics(question)
        else:  # pragma: no cover - exercised via stubs in unit tests
            start = perf_counter()
            chunks = await retrieval.retrieve(question)
            elapsed = (perf_counter() - start) * 1000
            outcome = RetrievalOutcome(
                candidates=chunks,
                reranked=chunks,
                retrieval_ms=elapsed,
                rerank_ms=0.0,
                cache_hit_embedding=False,
            )

        observe_stage("retrieval", outcome.retrieval_ms / 1000)
        observe_stage("rerank", outcome.rerank_ms / 1000)
        retrieval_span = trace.span(name="retrieval", input={"question": question})
        retrieval_span.end(
            output={
                "chunk_ids": [str(c["chunk_id"]) for c in outcome.candidates],
                "scores": [c.get("score") for c in outcome.candidates],
            },
            metadata={
                "retrieval_ms": round(outcome.retrieval_ms, 2),
                "cache_hit_embedding": outcome.cache_hit_embedding,
            },
        )
        rerank_span = trace.span(name="rerank", input={"num_candidates": len(outcome.candidates)})
        rerank_span.end(
            output={
                "chunk_ids": [str(c["chunk_id"]) for c in outcome.reranked],
                "scores": [c.get("rerank_score") for c in outcome.reranked],
            },
            metadata={"rerank_ms": round(outcome.rerank_ms, 2)},
        )
        return outcome

    async def _serve_cached_response(
        self,
        factory: async_sessionmaker[AsyncSession],
        conversation_id: uuid.UUID,
        question: str,
        cached: dict[str, Any],
        total_start: float,
    ) -> AsyncIterator[dict[str, Any]]:
        """Replay a cached ``{answer, citations}`` as a real-looking stream."""
        answer = cached.get("answer", "")
        citations = cached.get("citations", [])
        await self._persist_assistant_message(factory, conversation_id, answer, citations)

        for delta in _slice_text(answer):
            yield {"type": "delta", "text": delta}
        yield {
            "type": "citations",
            "conversation_id": str(conversation_id),
            "citations": citations,
        }

        record_cache("response", True)
        total_ms = (perf_counter() - total_start) * 1000
        observe_stage("total", total_ms / 1000)
        cached_ids = [str(c.get("chunk_id")) for c in citations]
        logger.info(
            "chat.request",
            query=question,
            retrieved_chunk_ids=cached_ids,
            reranked_chunk_ids=cached_ids,
            retrieval_ms=0.0,
            rerank_ms=0.0,
            generation_ms=0.0,
            total_ms=round(total_ms, 2),
            prompt_tokens=0,
            completion_tokens=0,
            estimated_cost_usd=0.0,
            cache_hit_embedding=False,
            cache_hit_response=True,
        )

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
            session.add(Message(conversation_id=conversation_id, role=_USER_ROLE, content=question))
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


def _slice_text(text: str, size: int = _REPLAY_CHUNK_CHARS) -> Iterator[str]:
    """Yield ``text`` in fixed-size slices (for replaying a cached answer)."""
    for start in range(0, len(text), size):
        yield text[start : start + size]


def _estimate_cost(prompt_tokens: int, completion_tokens: int, embedding_tokens: int) -> float:
    """Estimate the per-request USD cost from the configured price table."""
    return (
        prompt_tokens / 1000 * settings.llm_cost_prompt_per_1k_tokens
        + completion_tokens / 1000 * settings.llm_cost_completion_per_1k_tokens
        + embedding_tokens / 1000 * settings.embedding_cost_per_1k_tokens
    )


def _count_tokens(text: str) -> int:
    """Return the token count of ``text`` (for estimating embedding cost)."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding(settings.tiktoken_encoding)
    return len(_encoder.encode(text))


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
