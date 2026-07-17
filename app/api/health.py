"""Service health endpoint."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.shared.constants import APP_NAME, APP_VERSION

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Public health response contract."""

    status: Literal["ok"]
    service: str
    version: str
    time: datetime


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Report process health without checking external dependencies."""
    return HealthResponse(
        status="ok",
        service=APP_NAME,
        version=APP_VERSION,
        time=datetime.now(UTC),
    )
