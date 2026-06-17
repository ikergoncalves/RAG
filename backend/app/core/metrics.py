"""Prometheus metrics for the RAG service.

Metrics are registered on the default ``prometheus_client`` registry (re-exported
as :data:`REGISTRY`) and exposed at ``GET /metrics``. The helper functions are
the only intended way to mutate them, so call sites stay decoupled from the
metric objects and label names live in one place.

- :data:`REQUESTS` — request counter per endpoint and HTTP status code.
- :data:`STAGE_LATENCY` — histogram of pipeline-stage latency
  (``retrieval`` | ``rerank`` | ``generation`` | ``total``).
- :data:`CACHE_EVENTS` — cache lookups by cache (``embedding`` | ``response``)
  and result (``hit`` | ``miss``), so a hit *rate* can be derived.
- :data:`ESTIMATED_COST` — accumulated estimated LLM + embedding cost (USD).
"""

from prometheus_client import REGISTRY, Counter, Gauge, Histogram

__all__ = [
    "REGISTRY",
    "record_request",
    "observe_stage",
    "record_cache",
    "add_cost",
]

REQUESTS = Counter(
    "rag_requests_total",
    "Total HTTP requests handled, by endpoint and status code.",
    ["endpoint", "status_code"],
)

# Buckets span sub-millisecond cache hits up to multi-second LLM generation.
STAGE_LATENCY = Histogram(
    "rag_stage_latency_seconds",
    "Latency of each chat-pipeline stage, in seconds.",
    ["stage"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

CACHE_EVENTS = Counter(
    "rag_cache_events_total",
    "Cache lookups, by cache type and hit/miss result.",
    ["cache", "result"],
)

ESTIMATED_COST = Gauge(
    "rag_estimated_cost_usd_total",
    "Accumulated estimated LLM + embedding cost, in USD.",
)


def record_request(endpoint: str, status_code: int) -> None:
    """Increment the request counter for ``endpoint`` and ``status_code``."""
    REQUESTS.labels(endpoint=endpoint, status_code=str(status_code)).inc()


def observe_stage(stage: str, seconds: float) -> None:
    """Record a latency observation (seconds) for a pipeline ``stage``."""
    STAGE_LATENCY.labels(stage=stage).observe(seconds)


def record_cache(cache: str, hit: bool) -> None:
    """Increment the cache counter for ``cache`` with a hit/miss ``result``."""
    CACHE_EVENTS.labels(cache=cache, result="hit" if hit else "miss").inc()


def add_cost(usd: float) -> None:
    """Add ``usd`` to the accumulated estimated-cost gauge."""
    if usd:
        ESTIMATED_COST.inc(usd)
