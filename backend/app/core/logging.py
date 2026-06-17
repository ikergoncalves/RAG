"""Structured logging configuration (structlog).

In production (``settings.environment == "production"``) logs are emitted as
single-line JSON, suitable for log shippers and querying. In development they
are rendered with structlog's colored, human-readable console renderer.

:func:`configure_logging` is idempotent and is called once from the FastAPI
lifespan on startup. Application code obtains a logger via :func:`get_logger`
and logs with key/value pairs, e.g.::

    log = get_logger(__name__)
    log.info("chat.request", query=question, total_ms=12.3, ...)
"""

import logging
from typing import Any

import structlog

from app.core.config import settings


def configure_logging() -> None:
    """Configure structlog for JSON (prod) or colored console (dev) output."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Any
    if settings.environment == "production":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a structlog logger bound to ``name``."""
    return structlog.get_logger(name)
