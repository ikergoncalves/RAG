"""Smoke tests for ``GET /health``.

The backing-service checks are monkeypatched so the test runs without a live
PostgreSQL/Qdrant/Redis (e.g. in CI). The endpoint wiring, status code, and
response shape are still exercised end-to-end through the ASGI app.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import health as health_service


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _patch_checks(monkeypatch: pytest.MonkeyPatch, *, postgres: str, qdrant: str, redis: str) -> None:
    async def _postgres() -> str:
        return postgres

    async def _qdrant() -> str:
        return qdrant

    async def _redis() -> str:
        return redis

    monkeypatch.setattr(health_service, "check_postgres", _postgres)
    monkeypatch.setattr(health_service, "check_qdrant", _qdrant)
    monkeypatch.setattr(health_service, "check_redis", _redis)


def test_health_ok_when_all_dependencies_reachable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_checks(monkeypatch, postgres="ok", qdrant="ok", redis="ok")

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"]["name"] == "RAG"
    assert body["dependencies"] == {"postgres": "ok", "qdrant": "ok", "redis": "ok"}


def test_health_degraded_returns_503_when_a_dependency_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_checks(monkeypatch, postgres="ok", qdrant="error: ConnectionError", redis="ok")

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["qdrant"].startswith("error")
