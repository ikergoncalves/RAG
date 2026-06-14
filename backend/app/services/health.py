"""Connectivity checks for the application's backing services.

Each ``check_*`` coroutine performs the cheapest possible round-trip to its
dependency and returns ``"ok"`` on success. ``get_health`` runs them
concurrently and aggregates the result. The individual check functions are kept
at module level so tests can monkeypatch them.
"""

import asyncio
from dataclasses import dataclass

from sqlalchemy import text

from app.db.qdrant import qdrant_client
from app.db.redis import redis_client
from app.db.session import engine

OK = "ok"


@dataclass
class HealthReport:
    """Aggregated result of all dependency checks."""

    healthy: bool
    dependencies: dict[str, str]


async def check_postgres() -> str:
    """Run ``SELECT 1`` against PostgreSQL."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return OK


async def check_qdrant() -> str:
    """List collections to confirm Qdrant is reachable."""
    await qdrant_client.get_collections()
    return OK


async def check_redis() -> str:
    """Ping Redis."""
    await redis_client.ping()
    return OK


async def _safe(name: str, check) -> tuple[str, str]:
    """Run a check, converting any failure into an error label."""
    try:
        return name, await check()
    except Exception as exc:  # noqa: BLE001 - any failure means "not reachable"
        return name, f"error: {exc.__class__.__name__}"


async def get_health() -> HealthReport:
    """Run all dependency checks concurrently and aggregate the outcome."""
    checks = {
        "postgres": check_postgres,
        "qdrant": check_qdrant,
        "redis": check_redis,
    }
    results = await asyncio.gather(*(_safe(name, fn) for name, fn in checks.items()))
    dependencies = dict(results)
    healthy = all(status == OK for status in dependencies.values())
    return HealthReport(healthy=healthy, dependencies=dependencies)
