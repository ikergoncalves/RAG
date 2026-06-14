"""Pydantic response schemas for the health endpoint."""

from typing import Literal

from pydantic import BaseModel


class AppInfo(BaseModel):
    name: str
    version: str
    environment: str


class HealthResponse(BaseModel):
    """Public shape of ``GET /health``."""

    status: Literal["ok", "degraded"]
    app: AppInfo
    # Per-dependency status: "ok" when reachable, otherwise an error label.
    dependencies: dict[str, str]
