"""Service health endpoint."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.shared.constants import APP_NAME, APP_VERSION

router = APIRouter(tags=["系统检查"])


class HealthResponse(BaseModel):
    """Public health response contract."""

    status: Literal["ok"]
    service: str
    version: str
    time: datetime


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="检查后端服务是否正在运行",
    description="只检查应用进程是否正常，不查询数据库。返回 ok 表示后端已经成功启动。",
)
def get_health() -> HealthResponse:
    """Report process health without checking external dependencies."""
    return HealthResponse(
        status="ok",
        service=APP_NAME,
        version=APP_VERSION,
        time=datetime.now(UTC),
    )
