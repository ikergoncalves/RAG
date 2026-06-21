"""Redis client (async).

``import redis.asyncio`` resolves to the installed ``redis`` package via Python's
absolute-import rules, not to this module.
"""

import redis.asyncio as redis_asyncio

from app.core.config import settings

# Temporary startup diagnostics (remove once the startup hang is resolved):
# bracket the import-time client construction. from_url builds the connection
# pool lazily (no socket opened here), so both markers should print instantly.
print("[startup] db.redis: creating redis client...", flush=True)
redis_client = redis_asyncio.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
    # Fail fast on an unreachable Redis instead of blocking forever: bound both
    # the initial socket connect and subsequent socket reads (seconds).
    socket_connect_timeout=10,
    socket_timeout=10,
)
print("[startup] db.redis: redis client created", flush=True)
