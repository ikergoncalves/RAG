"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.retrieval import router as retrieval_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.metrics import record_request


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan hook.

    Configures structured logging on startup. Backing-service clients are
    created lazily, so there is nothing else to set up here yet.
    """
    configure_logging()
    get_logger(__name__).info(
        "app.startup",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def count_requests(request: Request, call_next):
        """Count every request by endpoint (route template) and status code."""
        response = await call_next(request)
        route = request.scope.get("route")
        endpoint = getattr(route, "path", None) or "unmatched"
        record_request(endpoint, response.status_code)
        return response

    app.include_router(health_router)
    app.include_router(documents_router)
    app.include_router(retrieval_router)
    app.include_router(chat_router)
    app.include_router(metrics_router)
    return app


app = create_app()
