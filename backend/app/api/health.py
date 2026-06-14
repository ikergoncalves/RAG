"""Health/readiness endpoint.

Returns ``200`` when the app and all backing services (PostgreSQL, Qdrant,
Redis) are reachable, and ``503`` when at least one dependency is down. The body
always reports the per-dependency status so callers can see what failed.
"""

from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.schemas.health import AppInfo, HealthResponse
from app.services.health import get_health

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "A dependency is unavailable"}},
)
async def health(response: Response) -> HealthResponse:
    report = await get_health()
    if not report.healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if report.healthy else "degraded",
        app=AppInfo(
            name=settings.app_name,
            version=settings.app_version,
            environment=settings.environment,
        ),
        dependencies=report.dependencies,
    )
