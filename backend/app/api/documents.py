"""Document ingestion endpoints.

- ``POST /documents``        upload a file; processing runs in the background
- ``GET  /documents``        list documents with status
- ``GET  /documents/{id}``   document details (+ chunk count)
- ``GET  /documents/{id}/chunks``  list a document's chunks with metadata
"""

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

from app.db.session import get_session
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.schemas.document import ChunkRead, DocumentDetail, DocumentRead
from app.services import ingestion, storage
from app.services.parsing import UnsupportedDocumentError, resolve_extension

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
