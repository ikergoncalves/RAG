"""PostgreSQL connectivity via async SQLAlchemy.

The engine is created lazily at import time; no connection is opened until a
session/connection is actually used. Models and migrations land in later phases.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(
    settings.postgres_dsn,
    pool_pre_ping=True,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a database session (used in later phases)."""
    async with AsyncSessionLocal() as session:
        yield session
