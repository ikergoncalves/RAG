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

# Temporary startup diagnostics (remove once the startup hang is resolved):
# bracket the import-time engine construction. create_async_engine does not
# open a connection, so this should print both markers instantly — if it does
# not, the engine construction itself is the culprit.
print("[startup] db.session: creating async engine...", flush=True)
engine = create_async_engine(
    settings.postgres_dsn,
    pool_pre_ping=True,
    future=True,
    # Aggressive timeouts so a connect/query against an unreachable PostgreSQL
    # fails fast instead of hanging the process forever (e.g. a misrouted DB on
    # a managed host). For asyncpg, "timeout" bounds connection establishment
    # and "command_timeout" bounds each statement (both in seconds).
    connect_args={"timeout": 10, "command_timeout": 10},
)
print("[startup] db.session: async engine created", flush=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a database session (used in later phases)."""
    async with AsyncSessionLocal() as session:
        yield session
