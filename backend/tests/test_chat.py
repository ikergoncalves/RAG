"""Tests for cited generation (ChatService + the Anthropic provider).

Layering mirrors ``test_retrieval.py``:

- Unit tests drive ``ChatService`` with a ``FakeLLMProvider`` and a stub
  retrieval service over in-memory SQLite, so they need neither an API key,
  PostgreSQL, nor Qdrant. They cover the streaming/persistence flow, citation
  enrichment, and the "no chunks -> never call the LLM" short-circuit.
- Integration tests exercise the *real* Anthropic provider end to end and skip
  themselves when ``ANTHROPIC_API_KEY`` is not set (same pattern as the phase 2/3
  OpenAI/Qdrant tests). Retrieval is stubbed with hand-crafted chunks so the test
  isolates generation + citation extraction. The headline invariant — every
  returned ``quote`` is a verbatim substring of its chunk — is the citation
  accuracy that phase 6/RAGAS will measure, so it is worth asserting now.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.models import Base, Conversation, Message
from app.services.chat import ChatService
from app.services.llm import INSUFFICIENT_CONTEXT_MESSAGE, LLMProvider

requires_anthropic = pytest.mark.skipif(
    not settings.anthropic_api_key,
    reason="ANTHROPIC_API_KEY is not set",
)


# --- Test doubles --------------------------------------------------------


class FakeLLMProvider(LLMProvider):
    """Streams a fixed answer in a few deltas and returns canned citations.

    Records call counts so tests can assert the LLM is *not* touched on the
    no-context path.
    """

    def __init__(self, answer: str, citations: list[dict[str, Any]] | None = None) -> None:
        self._answer = answer
        self._citations = citations or []
        self.generate_calls = 0
        self.extract_calls = 0

    async def generate_answer(self, question: str, context_chunks: list[dict[str, Any]]):
        self.generate_calls += 1
        # Emit in a few slices so the delta-accumulation path is exercised.
        chunk_size = max(1, len(self._answer) // 3)
        for start in range(0, len(self._answer), chunk_size):
            yield self._answer[start : start + chunk_size]

    async def extract_citations(
        self, question: str, answer: str, context_chunks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        self.extract_calls += 1
        return [dict(citation) for citation in self._citations]


class StubRetrieval:
    """Returns a fixed list of context chunks; duck-types ``RetrievalService``."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks = chunks
        self.calls = 0

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls += 1
        return [dict(chunk) for chunk in self._chunks]


# --- Fixtures / helpers --------------------------------------------------


def _run(body: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(body())


async def _make_session_factory() -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _chunk(
    content: str,
    *,
    chunk_id: str | None = None,
    document_id: str | None = None,
    filename: str = "guide.md",
    page: int | None = 1,
    section: str | None = "Intro",
) -> dict[str, Any]:
    """Build a retrieval-shaped context chunk (matches RetrievalService output)."""
    return {
        "chunk_id": chunk_id or str(uuid.uuid4()),
        "document_id": document_id or str(uuid.uuid4()),
        "document_filename": filename,
        "page_number": page,
        "section_path": section,
        "content": content,
        "score": 0.5,
        "rerank_score": 0.9,
    }


# --- Unit tests: ChatService with a fake provider ------------------------


def test_streaming_flow_persists_and_enriches_citations() -> None:
    """Deltas reconstruct the answer; the conversation/messages persist; citations
    are enriched with the source chunk's document/page/section metadata."""

    async def body() -> None:
        engine, factory = await _make_session_factory()
        chunk_id = str(uuid.uuid4())
        document_id = str(uuid.uuid4())
        chunk = _chunk(
            "Paris is the capital of France.",
            chunk_id=chunk_id,
            document_id=document_id,
            filename="geo.md",
            page=3,
            section="Capitals",
        )
        provider = FakeLLMProvider(
            answer="The capital of France is Paris [1].",
            citations=[
                {"number": 1, "chunk_id": chunk_id, "quote": "Paris is the capital of France."}
            ],
        )
        service = ChatService(
            llm_provider=provider,
            retrieval_service=StubRetrieval([chunk]),
            session_factory=factory,
        )

        try:
            items = [item async for item in service.ask("What is the capital of France?", None)]

            deltas = [item for item in items if item["type"] == "delta"]
            assert len(deltas) > 1  # streamed in multiple deltas
            assert "".join(d["text"] for d in deltas) == "The capital of France is Paris [1]."

            final = items[-1]
            assert final["type"] == "citations"
            assert final["conversation_id"]
            assert final["citations"] == [
                {
                    "number": 1,
                    "chunk_id": chunk_id,
                    "quote": "Paris is the capital of France.",
                    "document_id": document_id,
                    "document_name": "geo.md",
                    "page": 3,
                    "section": "Capitals",
                }
            ]

            assert provider.generate_calls == 1
            assert provider.extract_calls == 1

            # Persistence: exactly one conversation, a user message and an
            # assistant message carrying the serialized citations.
            async with factory() as session:
                result = await session.execute(select(Conversation))
                conversations = list(result.scalars().all())
                assert len(conversations) == 1
                assert str(conversations[0].id) == final["conversation_id"]

                result = await session.execute(select(Message).where(Message.role == "user"))
                user_messages = list(result.scalars().all())
                result = await session.execute(select(Message).where(Message.role == "assistant"))
                assistant_messages = list(result.scalars().all())
                assert len(user_messages) == 1
                assert len(assistant_messages) == 1
                assert user_messages[0].content == "What is the capital of France?"
                assert user_messages[0].citations is None
                assert assistant_messages[0].content == "The capital of France is Paris [1]."
                assert assistant_messages[0].citations == final["citations"]
                assert all(
                    message.conversation_id == conversations[0].id
                    for message in user_messages + assistant_messages
                )
        finally:
            await engine.dispose()

    _run(body)


def test_no_chunks_short_circuits_without_calling_llm() -> None:
    """With no retrieved context the LLM is never called: the fixed refusal is
    streamed and persisted, and the citations list is empty."""

    async def body() -> None:
        engine, factory = await _make_session_factory()
        provider = FakeLLMProvider(
            answer="this answer must never be used",
            citations=[{"number": 1, "chunk_id": "x", "quote": "y"}],
        )
        service = ChatService(
            llm_provider=provider,
            retrieval_service=StubRetrieval([]),
            session_factory=factory,
        )

        try:
            items = [item async for item in service.ask("anything at all?", None)]

            # The LLM was never touched (zero token cost).
            assert provider.generate_calls == 0
            assert provider.extract_calls == 0

            deltas = [item for item in items if item["type"] == "delta"]
            assert "".join(d["text"] for d in deltas) == INSUFFICIENT_CONTEXT_MESSAGE

            final = items[-1]
            assert final["type"] == "citations"
            assert final["citations"] == []

            async with factory() as session:
                result = await session.execute(select(Message).where(Message.role == "assistant"))
                assistant_messages = list(result.scalars().all())
                assert len(assistant_messages) == 1
                assert assistant_messages[0].content == INSUFFICIENT_CONTEXT_MESSAGE
                assert assistant_messages[0].citations == []
        finally:
            await engine.dispose()

    _run(body)


def test_existing_conversation_id_is_reused() -> None:
    """Passing a conversation id appends to it instead of creating a new one."""

    async def body() -> None:
        engine, factory = await _make_session_factory()
        async with factory() as session:
            conversation = Conversation()
            session.add(conversation)
            await session.commit()
            existing_id = conversation.id

        chunk = _chunk("Some content about widgets.")
        provider = FakeLLMProvider(
            answer="Widgets are described here [1].",
            citations=[
                {"number": 1, "chunk_id": chunk["chunk_id"], "quote": "Some content about widgets."}
            ],
        )
        service = ChatService(
            llm_provider=provider,
            retrieval_service=StubRetrieval([chunk]),
            session_factory=factory,
        )

        try:
            items = [item async for item in service.ask("Tell me about widgets.", existing_id)]
            assert items[-1]["conversation_id"] == str(existing_id)

            async with factory() as session:
                result = await session.execute(select(Conversation))
                conversations = list(result.scalars().all())
                assert len(conversations) == 1  # no new conversation created

                result = await session.execute(
                    select(Message).where(Message.conversation_id == existing_id)
                )
                messages = list(result.scalars().all())
                assert {message.role for message in messages} == {"user", "assistant"}
                assert len(messages) == 2
        finally:
            await engine.dispose()

    _run(body)


def test_snap_quote_repairs_normalized_whitespace() -> None:
    """A quote whose chunk newlines were normalized to spaces snaps back to the
    exact verbatim span; an exact substring is unchanged; a paraphrase is None."""
    from app.services.llm.anthropic_provider import _snap_quote_to_content

    content = "split long sections like this\none into several overlapping chunks"

    # The model collapsed the chunk's hard line-wrap newline into a space.
    snapped = _snap_quote_to_content("like this one into several", content)
    assert snapped == "like this\none into several"
    assert snapped in content  # repaired quote is a true substring

    exact = _snap_quote_to_content("several overlapping chunks", content)
    assert exact == "several overlapping chunks"
    assert _snap_quote_to_content("entirely different words", content) is None


# --- Integration tests: real Anthropic provider --------------------------


@requires_anthropic
def test_real_anthropic_covered_question_yields_verbatim_citations() -> None:
    """A question answered by the context produces citations whose quotes are
    verbatim substrings of the chunks they reference (citation accuracy)."""

    async def body() -> None:
        try:
            from app.services.llm.anthropic_provider import AnthropicLLMProvider

            provider = AnthropicLLMProvider()
        except Exception as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"Anthropic provider unavailable: {exc}")

        engine, factory = await _make_session_factory()
        chunks = [
            _chunk(
                # Hard line-wrap newline mid-content: the model normalizes it to a
                # space when quoting, so this exercises the verbatim-snap repair.
                "The Eiffel Tower is a wrought-iron lattice tower in Paris,\n"
                "completed in 1889 for the World's Fair.",
                filename="paris.md",
                page=1,
                section="Landmarks",
            ),
            _chunk(
                "The Louvre, on the Right Bank of the Seine, is the world's most-visited museum.",
                filename="paris.md",
                page=2,
                section="Museums",
            ),
        ]
        service = ChatService(
            llm_provider=provider,
            retrieval_service=StubRetrieval(chunks),
            session_factory=factory,
        )

        try:
            items = [
                item async for item in service.ask("When was the Eiffel Tower completed?", None)
            ]
            final = items[-1]
            assert final["type"] == "citations"

            citations = final["citations"]
            assert citations  # a covered question should be cited
            chunks_by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
            for citation in citations:
                source = chunks_by_id[citation["chunk_id"]]
                assert citation["quote"] in source["content"]
        finally:
            await engine.dispose()

    _run(body)


@requires_anthropic
def test_real_anthropic_unrelated_question_says_dont_know_without_citations() -> None:
    """A question unrelated to the context yields the refusal and no citations."""

    async def body() -> None:
        try:
            from app.services.llm.anthropic_provider import AnthropicLLMProvider

            provider = AnthropicLLMProvider()
        except Exception as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"Anthropic provider unavailable: {exc}")

        engine, factory = await _make_session_factory()
        chunks = [
            _chunk(
                "Photosynthesis is the process by which plants convert light energy into "
                "chemical energy stored in glucose."
            ),
            _chunk(
                "Chlorophyll absorbs light most strongly in the blue and red parts of the "
                "spectrum."
            ),
        ]
        service = ChatService(
            llm_provider=provider,
            retrieval_service=StubRetrieval(chunks),
            session_factory=factory,
        )

        try:
            items = [
                item
                async for item in service.ask(
                    "What was the closing share price of Acme Corp last Friday?", None
                )
            ]
            answer = "".join(item["text"] for item in items if item["type"] == "delta")
            assert "don't have enough information" in answer.lower()
            assert items[-1]["citations"] == []
        finally:
            await engine.dispose()

    _run(body)
