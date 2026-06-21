"""Langfuse tracing for the chat pipeline.

:class:`ChatService` creates one trace per request with nested spans for the
``retrieval``, ``rerank`` and ``generation`` stages, carrying chunk ids, scores,
latencies and token usage as span metadata.

Langfuse is entirely optional. When ``LANGFUSE_PUBLIC_KEY`` /
``LANGFUSE_SECRET_KEY`` are unset (or the SDK is unavailable, or the client
fails to initialize), :func:`get_observability` returns a service whose trace
and span handles are silent no-ops — the rest of the system behaves identically.
Every call into the real SDK is also wrapped defensively so a Langfuse hiccup
can never break a chat request.
"""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class _NoOpSpan:
    """Span handle used when tracing is disabled; every method is a no-op."""

    def end(self, **_kwargs: Any) -> None:
        return None


class _NoOpTrace:
    """Trace handle used when tracing is disabled."""

    def span(self, **_kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()

    def update(self, **_kwargs: Any) -> None:
        return None


class _LangfuseSpan:
    """Defensive wrapper around a Langfuse span; failures degrade to no-ops."""

    def __init__(self, span: Any) -> None:
        self._span = span

    def end(self, **kwargs: Any) -> None:
        try:
            self._span.end(**kwargs)
        except Exception as exc:  # pragma: no cover - SDK/version dependent
            logger.debug("Langfuse span.end failed: %s", exc)


class _LangfuseTrace:
    """Defensive wrapper around a Langfuse trace."""

    def __init__(self, trace: Any) -> None:
        self._trace = trace

    def span(self, **kwargs: Any) -> Any:
        try:
            return _LangfuseSpan(self._trace.span(**kwargs))
        except Exception as exc:  # pragma: no cover - SDK/version dependent
            logger.debug("Langfuse trace.span failed: %s", exc)
            return _NoOpSpan()

    def update(self, **kwargs: Any) -> None:
        try:
            self._trace.update(**kwargs)
        except Exception as exc:  # pragma: no cover - SDK/version dependent
            logger.debug("Langfuse trace.update failed: %s", exc)


class ObservabilityService:
    """Creates Langfuse traces, or no-op handles when tracing is disabled."""

    def __init__(self, client: Any = None) -> None:
        self._client = client

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def start_trace(self, name: str, **kwargs: Any) -> Any:
        """Start a trace, returning a real or no-op handle."""
        if self._client is None:
            return _NoOpTrace()
        try:
            return _LangfuseTrace(self._client.trace(name=name, **kwargs))
        except Exception as exc:  # pragma: no cover - SDK/version dependent
            logger.debug("Langfuse trace creation failed: %s", exc)
            return _NoOpTrace()

    def flush(self) -> None:
        """Flush buffered events to Langfuse (no-op when disabled)."""
        if self._client is None:
            return
        try:
            self._client.flush()
        except Exception as exc:  # pragma: no cover - SDK/version dependent
            logger.debug("Langfuse flush failed: %s", exc)


def _build() -> ObservabilityService:
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return ObservabilityService(None)
    # Import the SDK lazily (only when tracing is actually configured) so it
    # never loads on the application's startup/import path. The SDK is optional;
    # absence (or a bad version) degrades to a silent no-op.
    try:
        from langfuse import Langfuse
    except Exception as exc:  # pragma: no cover - import guard
        logger.warning("Langfuse SDK unavailable; tracing disabled: %s", exc)
        return ObservabilityService(None)
    try:
        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception as exc:  # pragma: no cover - SDK/version dependent
        logger.warning("Langfuse initialization failed; tracing disabled: %s", exc)
        return ObservabilityService(None)
    logger.info("Langfuse tracing enabled (host=%s)", settings.langfuse_host)
    return ObservabilityService(client)


_default_observability: ObservabilityService | None = None


def get_observability() -> ObservabilityService:
    """Return the shared observability service (built once per process)."""
    global _default_observability
    if _default_observability is None:
        _default_observability = _build()
    return _default_observability
