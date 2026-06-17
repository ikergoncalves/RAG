"""Chat endpoint (Server-Sent Events).

``POST /chat`` runs the retrieve -> generate -> cite pipeline and streams the
result as SSE. Each event is a ``data: <json>`` line: a sequence of
``{"type": "delta", "text": ...}`` events as the answer is generated, followed by
a terminal ``{"type": "citations", "conversation_id": ..., "citations": [...]}``.

Returns ``503`` when ``ANTHROPIC_API_KEY`` is not configured (generation is
impossible without it).
"""

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.schemas.chat import ChatRequest
from app.services.cache import get_default_cache
from app.services.chat import ChatService

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """Stream a cited answer for ``request.question`` as Server-Sent Events."""
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY is not configured",
        )

    conversation_id: uuid.UUID | None = None
    if request.conversation_id:
        try:
            conversation_id = uuid.UUID(request.conversation_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="conversation_id must be a valid UUID",
            ) from exc

    service = ChatService(cache_service=get_default_cache())

    async def event_stream() -> AsyncIterator[str]:
        async for item in service.ask(request.question, conversation_id):
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
