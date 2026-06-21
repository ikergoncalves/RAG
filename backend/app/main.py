"""FastAPI application entrypoint."""

# Temporary startup diagnostics: a print is interleaved between every top-level
# import to pinpoint exactly which import hangs on a constrained/misconfigured
# host (the last marker printed names the import that was in progress).
# Interleaving statements breaks the "imports at top of file" rule, so E402 is
# silenced file-wide for now. Remove this instrumentation once the hang is found.
# ruff: noqa: E402

print("[startup] main: begin imports", flush=True)

from contextlib import asynccontextmanager

print("[startup] main: contextlib done", flush=True)

from fastapi import FastAPI, Request

print("[startup] main: fastapi done", flush=True)

from fastapi.middleware.cors import CORSMiddleware

print("[startup] main: fastapi.middleware.cors done", flush=True)

from app.api.chat import router as chat_router

print("[startup] main: app.api.chat done", flush=True)

from app.api.documents import router as documents_router

print("[startup] main: app.api.documents done", flush=True)

from app.api.health import router as health_router

print("[startup] main: app.api.health done", flush=True)

from app.api.metrics import router as metrics_router

print("[startup] main: app.api.metrics done", flush=True)

from app.api.retrieval import router as retrieval_router

print("[startup] main: app.api.retrieval done", flush=True)

from app.core.config import settings

print("[startup] main: app.core.config done", flush=True)

from app.core.logging import configure_logging, get_logger

print("[startup] main: app.core.logging done", flush=True)

from app.core.metrics import record_request

print("[startup] main: app.core.metrics done — app.main imported", flush=True)


def _log_startup_memory() -> None:
    """Temporary diagnostic: log the process's peak RSS once startup completes.

    Uses the stdlib ``resource`` module (Linux/Unix only; a silent no-op on
    other platforms), so it adds no dependency. ``ru_maxrss`` is in kilobytes
    on Linux. Remove together with the import marker above once startup memory
    is confirmed healthy.
    """
    try:
        import resource

        max_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        get_logger(__name__).info("app.startup.memory", max_rss_mb=round(max_rss_kb / 1024, 1))
    except Exception:  # pragma: no cover - platform/SDK dependent
        pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan hook.

    Configures structured logging on startup. Backing-service clients are
    created lazily, so there is nothing else to set up here yet.
    """
    # Temporary startup diagnostics (remove once the startup hang is resolved):
    # explicit markers bracket the lifespan body so that if any call inside it
    # hangs, the last marker printed pinpoints exactly where.
    print("[startup] lifespan: begin", flush=True)
    configure_logging()
    print("[startup] lifespan: logging configured", flush=True)
    get_logger(__name__).info(
        "app.startup",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
    _log_startup_memory()
    print("[startup] lifespan: startup complete, yielding", flush=True)
    yield
    print("[shutdown] lifespan: end", flush=True)


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
