"""Pydantic schemas for the chat (SSE generation) endpoint."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Body of ``POST /chat``.

    ``conversation_id`` continues an existing conversation; omit it (or send
    ``null``) to start a new one.
    """

    question: str = Field(..., min_length=1)
    conversation_id: str | None = None
