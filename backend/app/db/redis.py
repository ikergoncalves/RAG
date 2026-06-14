"""Redis client (async).

``import redis.asyncio`` resolves to the installed ``redis`` package via Python's
absolute-import rules, not to this module.
"""

import redis.asyncio as redis_asyncio

from app.core.config import settings

redis_client = redis_asyncio.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
)
