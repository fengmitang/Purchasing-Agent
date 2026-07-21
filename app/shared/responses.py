"""Models and factories for public API response envelopes."""

from typing import Any

from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from app.shared.errors import ErrorCode


class ResponseMeta(BaseModel):
    """Metadata attached to successful API responses."""

    request_id: str


class SuccessResponse[DataT](BaseModel):
    """Standard successful single-object response."""

    data: DataT
    meta: ResponseMeta


class PageInfo(BaseModel):
    """Stable page metadata for bounded list responses."""

    number: int
    size: int
    total: int


class PaginatedResponse[DataT](BaseModel):
    """Standard successful list response."""

    data: list[DataT]
    page: PageInfo
    meta: ResponseMeta


class ErrorBody(BaseModel):
    """Safe public error information."""

    code: ErrorCode
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)
    request_id: str


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    error: ErrorBody


def error_json_response(
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    request_id: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """Build a JSON error response that exactly follows the public contract."""
    payload = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or [],
            request_id=request_id,
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))
