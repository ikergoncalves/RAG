"""Anthropic (Claude) implementation of :class:`LLMProvider`.

Generation streams a cited answer from ``settings.generation_model`` (default
``claude-sonnet-4-6``). Citation extraction is a separate, non-streaming call to
a cheaper model (``settings.citation_extraction_model``, default
``claude-haiku-4-5-20251001``) that is forced — via ``tool_choice`` — to return a
structured ``{citations: [{number, chunk_id, quote}]}`` payload.

Nothing about the Anthropic SDK leaks past this module: callers depend only on
:class:`LLMProvider`.
"""

import logging
import re
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import anthropic

from app.core.config import settings
from app.services.llm.base import INSUFFICIENT_CONTEXT_MESSAGE, LLMProvider

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

# Generous enough for a grounded, cited answer without risking SDK HTTP timeouts
# (generation streams, so this is just a ceiling).
_GENERATION_MAX_TOKENS = 2048
# Citation extraction returns a compact JSON payload; this is plenty.
_CITATION_MAX_TOKENS = 2048

_GENERATION_SYSTEM_PROMPT = (
    "You are a question-answering assistant. Answer the user's question using ONLY "
    "the information in the numbered context passages provided in the user message.\n\n"
    "Rules:\n"
    "- Rely solely on the numbered passages [1]..[n]. Never use outside knowledge.\n"
    "- Insert citation markers like [1] or [2] inline at every point where you use a "
    "passage. Cite the specific passage(s) that support each statement.\n"
    "- If the passages do not contain enough information to answer the question, reply "
    f'with exactly: "{INSUFFICIENT_CONTEXT_MESSAGE}" and nothing else. '
    "Do not invent citations in that case.\n"
    "- Keep the answer concise and directly grounded in the passages."
)

_CITATION_SYSTEM_PROMPT = (
    "You extract citations from an answer that was written from numbered context "
    "passages. For every [n] marker in the answer, produce one citation object with:\n"
    "- number: the marker number n.\n"
    "- chunk_id: the chunk id of passage [n], copied exactly from the context.\n"
    "- quote: a SHORT excerpt copied VERBATIM (character for character) from that "
    "passage's content that supports the cited statement. The quote must appear "
    "exactly in the passage content — do not paraphrase, fix, or shorten words.\n\n"
    "Only cite passages that appear in the context. If the answer contains no [n] "
    "markers, return an empty list. Always respond by calling the record_citations tool."
)

# Forced tool: constrains the extraction call to a structured citations payload.
_CITATION_TOOL: dict[str, Any] = {
    "name": "record_citations",
    "description": "Record the citations that support the generated answer.",
    "input_schema": {
        "type": "object",
        "properties": {
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "number": {
                            "type": "integer",
                            "description": "The [n] marker number in the answer.",
                        },
                        "chunk_id": {
                            "type": "string",
                            "description": "The chunk id of the cited passage, copied "
                            "exactly from the context.",
                        },
                        "quote": {
                            "type": "string",
                            "description": "A verbatim substring of that passage's "
                            "content supporting the citation.",
                        },
                    },
                    "required": ["number", "chunk_id", "quote"],
                },
            }
        },
        "required": ["citations"],
    },
}


class AnthropicLLMProvider(LLMProvider):
    """Cited generation backed by the Anthropic Messages API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        generation_model: str | None = None,
        citation_extraction_model: str | None = None,
        client: "AsyncAnthropic | None" = None,
    ) -> None:
        api_key = api_key or settings.anthropic_api_key
        if not api_key and client is None:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not configured; cannot create AnthropicLLMProvider"
            )
        self._generation_model = generation_model or settings.generation_model
        self._citation_model = citation_extraction_model or settings.citation_extraction_model
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key)

    async def generate_answer(
        self,
        question: str,
        context_chunks: list[dict[str, Any]],
        *,
        usage_sink: dict[str, int] | None = None,
    ) -> AsyncIterator[str]:
        user_message = f"{_format_context(context_chunks)}\n\nQuestion: {question}"
        async with self._client.messages.stream(
            model=self._generation_model,
            max_tokens=_GENERATION_MAX_TOKENS,
            system=_GENERATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
            if usage_sink is not None:
                # The final message carries the authoritative token usage for the
                # streamed completion; surface it for cost tracking / logging.
                try:
                    usage = (await stream.get_final_message()).usage
                    usage_sink["prompt_tokens"] = usage.input_tokens
                    usage_sink["completion_tokens"] = usage.output_tokens
                except Exception as exc:  # pragma: no cover - SDK/network dependent
                    logger.warning("Failed to read generation token usage: %s", exc)

    async def extract_citations(
        self, question: str, answer: str, context_chunks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        content_by_id = {
            str(chunk["chunk_id"]): chunk.get("content", "") for chunk in context_chunks
        }
        user_message = (
            f"{_format_context_with_ids(context_chunks)}\n\n"
            f"Question: {question}\n\n"
            f"Answer to cite:\n{answer}"
        )
        response = await self._client.messages.create(
            model=self._citation_model,
            max_tokens=_CITATION_MAX_TOKENS,
            system=_CITATION_SYSTEM_PROMPT,
            tools=[_CITATION_TOOL],
            tool_choice={"type": "tool", "name": _CITATION_TOOL["name"]},
            messages=[{"role": "user", "content": user_message}],
        )

        raw = _extract_tool_citations(response)
        citations: list[dict[str, Any]] = []
        for item in raw:
            chunk_id = str(item.get("chunk_id", ""))
            if chunk_id not in content_by_id:
                logger.warning(
                    "Discarding citation with unknown chunk_id %r (not in context)",
                    chunk_id,
                )
                continue
            quote = item.get("quote", "")
            # Repair the quote to the exact verbatim span in the chunk: models
            # tend to normalize the chunk's hard line-wrap newlines into spaces,
            # which would break a strict substring check used for highlighting.
            snapped = _snap_quote_to_content(quote, content_by_id[chunk_id])
            if snapped is None:
                logger.warning(
                    "Citation quote not found verbatim in chunk %s; keeping model quote",
                    chunk_id,
                )
            citations.append(
                {
                    "number": item.get("number"),
                    "chunk_id": chunk_id,
                    "quote": snapped if snapped is not None else quote,
                }
            )
        return citations


def _format_context(context_chunks: list[dict[str, Any]]) -> str:
    """Number the chunks ``[1]..[n]`` for the generation prompt."""
    blocks = [
        f"[{index}] {chunk.get('content', '')}"
        for index, chunk in enumerate(context_chunks, start=1)
    ]
    return "Context passages:\n\n" + "\n\n".join(blocks)


def _format_context_with_ids(context_chunks: list[dict[str, Any]]) -> str:
    """Number the chunks and expose each chunk id for the extraction prompt."""
    blocks = [
        f"[{index}] (chunk_id: {chunk.get('chunk_id')})\n{chunk.get('content', '')}"
        for index, chunk in enumerate(context_chunks, start=1)
    ]
    return "Context passages:\n\n" + "\n\n".join(blocks)


def _snap_quote_to_content(quote: str, content: str) -> str | None:
    """Return the exact substring of ``content`` corresponding to ``quote``.

    Models tend to normalize whitespace when quoting — most commonly collapsing
    the hard line-wrap newlines inside a chunk into spaces — which makes the
    quote fail a strict substring check against the stored chunk text and breaks
    offset-based highlighting in the source viewer. This repairs such quotes by
    matching the quote's tokens against ``content`` with flexible whitespace and
    returning the verbatim span (or ``None`` when the tokens are not found, e.g.
    a paraphrased or hallucinated quote).
    """
    if not quote or not content:
        return None
    if quote in content:
        return quote
    tokens = quote.split()
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    match = re.search(pattern, content)
    return match.group(0) if match else None


def _extract_tool_citations(response: Any) -> list[dict[str, Any]]:
    """Pull the ``citations`` list out of the forced tool-use response block."""
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_input = block.input or {}
            citations = tool_input.get("citations", [])
            return citations if isinstance(citations, list) else []
    return []
