"""Qdrant vector database client (async)."""

from qdrant_client import AsyncQdrantClient

from app.core.config import settings

# Temporary startup diagnostics (remove once the startup hang is resolved):
# bracket the import-time client construction so a hang *inside* the
# constructor (e.g. a synchronous DNS/handshake) is pinpointed to this line.
print(
    f"[startup] db.qdrant: constructing AsyncQdrantClient (url={settings.qdrant_url})...",
    flush=True,
)
qdrant_client = AsyncQdrantClient(
    url=settings.qdrant_url,
    api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
    check_compatibility=False,
    # Bound every Qdrant request (seconds) so an unreachable/slow Qdrant fails
    # fast instead of hanging the caller indefinitely.
    timeout=10,
)
print("[startup] db.qdrant: AsyncQdrantClient constructed", flush=True)
