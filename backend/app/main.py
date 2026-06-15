"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.retrieval import router as retrieval_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan hook.

    Backing-service clients are created lazily, so there is nothing to do on
    startup yet. Resource setup/teardown (e.g. closing pools) lands here in
    later phases.
    """
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

    app.include_router(health_router)
    app.include_router(documents_router)
    app.include_router(retrieval_router)
    return app


app = create_app()
