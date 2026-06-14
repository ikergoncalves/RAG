"""Pydantic schemas for documents and chunks."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus


class ChunkRead(BaseModel):
    """A chunk with its full citation metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int
    page_number: int | None
    section_path: str | None
    char_start: int
    char_end: int
    # Timestamp of the chunk's last successful upsert into Qdrant (None until indexed).
    embedded_at: datetime | None


class DocumentRead(BaseModel):
    """Summary view of a document (used in lists)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    status: DocumentStatus
    uploaded_at: datetime


class DocumentDetail(DocumentRead):
    """Document view with the number of persisted chunks."""

    chunk_count: int


class IndexingResult(BaseModel):
    """Outcome of a (re-)indexing run for a document."""

    document_id: uuid.UUID
    indexed_chunks: int
