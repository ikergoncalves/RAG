"""Document ingestion endpoints.

- ``POST   /documents``        upload a file; processing runs in the background
- ``GET    /documents``        list documents with status
- ``GET    /documents/{id}``   document details (+ chunk count)
- ``DELETE /documents/{id}``   remove a document (chunks, vectors and file)
- ``GET    /documents/{id}/chunks``  list a document's chunks with metadata
- ``POST   /documents/{id}/index``   re-embed and re-index the document into Qdrant
- ``GET    /chunks/{id}``      fetch a single chunk by id (source viewer)
"""

import logging
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.schemas.document import (
    ChunkRead,
    DocumentDetail,
    DocumentRead,
    IndexingResult,
)
from app.services import indexing, ingestion, storage, vector_store
from app.services.parsing import UnsupportedDocumentError, resolve_extension

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])


@router.post("/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> Document:
    """Accept a file upload and schedule its ingestion (parse -> chunk -> persist)."""
    filename = file.filename or "upload"
    try:
        resolve_extension(filename, file.content_type)
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty"
        )

    document = Document(
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        status=DocumentStatus.pending.value,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)

    storage.save_upload(document.id, filename, data)
    background_tasks.add_task(ingestion.process_document, document.id)
    return document


@router.get("/documents", response_model=list[DocumentRead])
async def list_documents(session: AsyncSession = Depends(get_session)) -> list[Document]:
    result = await session.execute(select(Document).order_by(Document.uploaded_at.desc()))
    return list(result.scalars().all())


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> DocumentDetail:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunk_count = await session.scalar(
        select(func.count(Chunk.id)).where(Chunk.document_id == document_id)
    )
    return DocumentDetail(
        id=document.id,
        filename=document.filename,
        content_type=document.content_type,
        status=DocumentStatus(document.status),
        uploaded_at=document.uploaded_at,
        chunk_count=chunk_count or 0,
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> None:
    """Delete a document together with its chunks, vectors and source file.

    The chunk rows are removed by the ``ON DELETE CASCADE`` on the foreign key.
    Removing the Qdrant points and the on-disk file is best-effort: a failure
    there is logged but does not block deletion of the document record (the
    vectors would otherwise be orphaned but unreachable, and a stale file is
    harmless).
    """
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    filename = document.filename
    await session.delete(document)
    await session.commit()

    try:
        await vector_store.delete_document_points(settings.qdrant_collection, str(document_id))
    except Exception:
        logger.exception("Failed to delete Qdrant points for document %s", document_id)

    try:
        storage.delete_upload(document_id, filename)
    except OSError:
        logger.exception("Failed to delete source file for document %s", document_id)


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkRead])
async def list_document_chunks(
    document_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[Chunk]:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    result = await session.execute(
        select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
    )
    return list(result.scalars().all())


@router.post("/documents/{document_id}/index", response_model=IndexingResult)
async def index_document(
    document_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> IndexingResult:
    """Re-embed every chunk of a document and (re-)index it into Qdrant.

    Idempotent: points are upserted by chunk id, so re-indexing never creates
    duplicates. Returns ``503`` when no embedding provider is configured (e.g. a
    missing ``OPENAI_API_KEY``).
    """
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        indexed = await indexing.index_document(document_id, force=True)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    return IndexingResult(document_id=document_id, indexed_chunks=indexed)


@router.get("/chunks/{chunk_id}", response_model=ChunkRead)
async def get_chunk(
    chunk_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> Chunk:
    """Return a single chunk with its full citation metadata.

    Backs the source viewer: given a citation's ``chunk_id`` the frontend fetches
    the chunk's content (and ``char_start``/``char_end``) to display the original
    passage with the cited quote highlighted.
    """
    chunk = await session.get(Chunk, chunk_id)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")
    return chunk
