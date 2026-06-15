"""Pydantic schemas for the retrieval (debug) endpoint."""

import uuid

from pydantic import BaseModel, Field


class RetrieveRequest(BaseModel):
    """Body of ``POST /retrieve``."""

    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)
    # Restrict retrieval to these documents (payload filter); null = all documents.
    document_ids: list[str] | None = None


class RetrievedChunk(BaseModel):
    """A retrieved chunk with its fusion and re-ranking scores plus metadata."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    page_number: int | None
    section_path: str | None
    content: str
    # Reciprocal Rank Fusion score from the first-stage hybrid search.
    score: float
    # Cross-encoder relevance score from the re-ranking stage.
    rerank_score: float


class RetrieveResponse(BaseModel):
    """Result of ``POST /retrieve``: the re-ranked top-k chunks."""

    query: str
    results: list[RetrievedChunk]
