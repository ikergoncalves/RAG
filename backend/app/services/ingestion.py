"""Ingestion orchestration: parse -> chunk -> persist.

``process_document`` is run as a FastAPI background task after upload. The
CPU/IO-bound parsing and chunking run in a worker thread so the event loop stays
responsive.
"""

import asyncio
import logging
import uuid
from pathlib import Path

from app.db.session import AsyncSessionLocal
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.services import storage
from app.services.chunking import ChunkData, chunk_blocks
from app.services.parsing import parse_document

logger = logging.getLogger(__name__)


def build_chunks(path: str | Path, *, filename: str, content_type: str | None) -> list[ChunkData]:
    """Parse a source file and split it into chunks (synchronous, CPU-bound)."""
    blocks = parse_document(path, filename=filename, content_type=content_type)
    return chunk_blocks(blocks)


async def process_document(document_id: uuid.UUID) -> None:
    """Parse, chunk and persist a document, updating its status along the way."""
    async with AsyncSessionLocal() as session:
        document = await session.get(Document, document_id)
        if document is None:
            logger.warning("process_document: document %s not found", document_id)
            return

        document.status = DocumentStatus.processing.value
        await session.commit()

        try:
            path = storage.storage_path(document_id, document.filename)
            chunks = await asyncio.to_thread(
                build_chunks,
                path,
                filename=document.filename,
                content_type=document.content_type,
            )
            session.add_all(
                Chunk(
                    document_id=document_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    page_number=chunk.page_number,
                    section_path=chunk.section_path,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                )
                for chunk in chunks
            )
            document.status = DocumentStatus.indexed.value
            await session.commit()
            logger.info("Indexed document %s (%d chunks)", document_id, len(chunks))
        except Exception:
            logger.exception("Failed to process document %s", document_id)
            await session.rollback()
            failed = await session.get(Document, document_id)
            if failed is not None:
                failed.status = DocumentStatus.failed.value
                await session.commit()
