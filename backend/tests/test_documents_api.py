"""Tests for the document/chunk HTTP endpoints added in phase 5.

Covers the two routes the frontend source viewer and document manager rely on:

- ``GET /chunks/{id}`` returns a single chunk with its citation metadata.
- ``DELETE /documents/{id}`` removes the document and cascades to its chunks,
  with best-effort cleanup of the Qdrant points and the on-disk source file.

The app is exercised through its real ASGI stack (httpx ``ASGITransport``) with
the ``get_session`` dependency overridden onto in-memory SQLite, mirroring the
asyncio-driven style of ``test_chat.py`` (no pytest-asyncio). Qdrant and the
filesystem are stubbed so the tests need neither a live vector store nor disk.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api import documents as documents_api
from app.db.session import get_session
from app.main import app
from app.models import Base
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus


def _run(body: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(body())


async def _setup() -> tuple[AsyncEngine, async_sessionmaker]:
    """Create an in-memory schema and route ``get_session`` to it."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite ignores ``ON DELETE CASCADE`` unless foreign keys are enabled per
    # connection; turn them on so the delete cascade matches Postgres behaviour.
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncIterator[Any]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    return engine, factory


def _teardown() -> None:
    app.dependency_overrides.pop(get_session, None)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_document_with_chunk(
    factory: async_sessionmaker,
) -> tuple[uuid.UUID, uuid.UUID]:
    async with factory() as session:
        document = Document(
            filename="guide.md",
            content_type="text/markdown",
            status=DocumentStatus.indexed.value,
        )
        session.add(document)
        await session.flush()
        chunk = Chunk(
            document_id=document.id,
            chunk_index=0,
            content="Paris is the capital of France.",
            token_count=7,
            page_number=3,
            section_path="Geography > Capitals",
            char_start=10,
            char_end=41,
        )
        session.add(chunk)
        await session.commit()
        return document.id, chunk.id


def test_get_chunk_returns_metadata() -> None:
    async def body() -> None:
        engine, factory = await _setup()
        try:
            _, chunk_id = await _seed_document_with_chunk(factory)
            async with _client() as client:
                response = await client.get(f"/chunks/{chunk_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == str(chunk_id)
            assert data["content"] == "Paris is the capital of France."
            assert data["page_number"] == 3
            assert data["section_path"] == "Geography > Capitals"
            assert data["char_start"] == 10
            assert data["char_end"] == 41
        finally:
            _teardown()
            await engine.dispose()

    _run(body)


def test_get_chunk_missing_returns_404() -> None:
    async def body() -> None:
        engine, _ = await _setup()
        try:
            async with _client() as client:
                response = await client.get(f"/chunks/{uuid.uuid4()}")
            assert response.status_code == 404
        finally:
            _teardown()
            await engine.dispose()

    _run(body)


def test_delete_document_removes_chunks_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def body() -> None:
        engine, factory = await _setup()

        deleted_points: list[tuple[str, str]] = []
        deleted_files: list[uuid.UUID] = []

        async def _fake_delete_points(collection: str, document_id: str) -> None:
            deleted_points.append((collection, document_id))

        def _fake_delete_upload(document_id: uuid.UUID, filename: str) -> None:
            deleted_files.append(document_id)

        monkeypatch.setattr(
            documents_api.vector_store, "delete_document_points", _fake_delete_points
        )
        monkeypatch.setattr(documents_api.storage, "delete_upload", _fake_delete_upload)

        try:
            document_id, chunk_id = await _seed_document_with_chunk(factory)
            async with _client() as client:
                response = await client.delete(f"/documents/{document_id}")
                assert response.status_code == 204

                # The document and its chunk are gone (cascade).
                assert (await client.get(f"/chunks/{chunk_id}")).status_code == 404
                assert (await client.get(f"/documents/{document_id}")).status_code == 404

            # Best-effort cleanup of vectors and the source file was attempted.
            assert deleted_points == [(documents_api.settings.qdrant_collection, str(document_id))]
            assert deleted_files == [document_id]
        finally:
            _teardown()
            await engine.dispose()

    _run(body)


def test_delete_missing_document_returns_404() -> None:
    async def body() -> None:
        engine, _ = await _setup()
        try:
            async with _client() as client:
                response = await client.delete(f"/documents/{uuid.uuid4()}")
            assert response.status_code == 404
        finally:
            _teardown()
            await engine.dispose()

    _run(body)
