"""Vector indexing job: embed chunks and upsert them into Qdrant.

For a given document this reads its chunks from PostgreSQL, generates a dense
embedding (via :class:`EmbeddingProvider`) and a sparse BM25 vector (via
FastEmbed) for each, and upserts them into the hybrid Qdrant collection using
the chunk's id as the point id. After a successful upsert the chunk's
``embedded_at`` is set so it is not reprocessed on the next run.

Idempotency: the point id equals the chunk id, so re-indexing a chunk overwrites
its point instead of creating a duplicate.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from qdrant_client import AsyncQdrantClient, models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import AsyncSessionLocal
from app.models.chunk import Chunk
from app.models.document import Document
from app.services import vector_store
from app.services.embeddings import EmbeddingProvider, get_default_embedding_provider

logger = logging.getLogger(__name__)


async def index_document(
    document_id: uuid.UUID,
    *,
    force: bool = False,
    embedding_provider: EmbeddingProvider | None = None,
    sparse_embedder: vector_store.SparseEmbedder | None = None,
    collection_name: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    client: AsyncQdrantClient | None = None,
) -> int:
    """Index a document's chunks into Qdrant and return how many were indexed.

    By default only chunks that have never been indexed (``embedded_at IS NULL``)
    are processed. Pass ``force=True`` to re-index every chunk of the document
    (used by the manual re-index endpoint); upserts are idempotent so this never
    duplicates points.
    """
    factory = session_factory or AsyncSessionLocal
    async with factory() as session:
        document = await session.get(Document, document_id)
        if document is None:
            logger.warning("index_document: document %s not found", document_id)
            return 0

        stmt = select(Chunk).where(Chunk.document_id == document_id)
        if not force:
            stmt = stmt.where(Chunk.embedded_at.is_(None))
        stmt = stmt.order_by(Chunk.chunk_index)
        chunks = list((await session.execute(stmt)).scalars().all())
        if not chunks:
            logger.info("index_document: nothing to index for document %s", document_id)
            return 0

        provider = embedding_provider or get_default_embedding_provider()
        sparse = sparse_embedder or vector_store.get_default_sparse_embedder()
        collection = await vector_store.ensure_collection(collection_name, client=client)

        points = await _build_points(document, chunks, provider, sparse)
        await vector_store.upsert_points(collection, points, client=client)

        now = datetime.now(timezone.utc)
        for chunk in chunks:
            chunk.embedded_at = now
        await session.commit()

    logger.info(
        "Indexed %d chunk(s) of document %s into Qdrant collection %r",
        len(chunks),
        document_id,
        collection,
    )
    return len(chunks)


async def _build_points(
    document: Document,
    chunks: list[Chunk],
    provider: EmbeddingProvider,
    sparse: vector_store.SparseEmbedder,
) -> list[models.PointStruct]:
    """Embed chunks (dense + sparse) and assemble Qdrant points off the event loop."""
    texts = [chunk.content for chunk in chunks]
    # Both embedders block (network / CPU); run them in worker threads.
    dense_vectors = await asyncio.to_thread(provider.embed, texts)
    sparse_vectors = await asyncio.to_thread(sparse.embed, texts)

    points: list[models.PointStruct] = []
    for chunk, dense, sparse_vector in zip(
        chunks, dense_vectors, sparse_vectors, strict=True
    ):
        points.append(
            models.PointStruct(
                id=str(chunk.id),
                vector={
                    vector_store.DENSE_VECTOR_NAME: dense,
                    vector_store.SPARSE_VECTOR_NAME: sparse_vector,
                },
                payload={
                    "document_id": str(document.id),
                    "document_filename": document.filename,
                    "page_number": chunk.page_number,
                    "section_path": chunk.section_path,
                    "content": chunk.content,
                },
            )
        )
    return points
