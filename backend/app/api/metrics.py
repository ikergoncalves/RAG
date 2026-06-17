"""Prometheus metrics endpoint.

``GET /metrics`` exposes the default ``prometheus_client`` registry in the
text exposition format, so Prometheus can scrape request counts, per-stage
latency histograms, cache hit/miss counters and the accumulated cost gauge.
"""

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.metrics import REGISTRY

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    """Return the current metrics in the Prometheus exposition format."""
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
