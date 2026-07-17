"""FastAPI exception handlers for stable, safe API errors."""

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.shared.errors import HTTP_STATUS_BY_ERROR_CODE, DomainError, ErrorCode
from app.shared.request_context import get_request_id
from app.shared.responses import error_json_response


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", get_request_id())


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return validation locations without echoing rejected input values."""
    details: list[dict[str, Any]] = [
        {
            "location": list(error.get("loc", ())),
            "message": error.get("msg", "Invalid value"),
            "type": error.get("type", "validation_error"),
        }
        for error in exc.errors()
    ]
    return error_json_response(
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        request_id=_request_id(request),
        details=details,
    )


async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Map a controlled domain failure to its documented status and code."""
    return error_json_response(
        status_code=HTTP_STATUS_BY_ERROR_CODE[exc.code],
        code=exc.code,
        message=exc.message,
        request_id=_request_id(request),
        details=exc.details,
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Normalize framework HTTP errors without exposing internal detail."""
    code_by_status = {
        401: ErrorCode.UNAUTHENTICATED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.RESOURCE_NOT_FOUND,
        409: ErrorCode.STATE_CONFLICT,
        422: ErrorCode.VALIDATION_ERROR,
        429: ErrorCode.RATE_LIMITED,
    }
    code = code_by_status.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    message = "Resource not found" if exc.status_code == 404 else "Request could not be processed"
    return error_json_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        request_id=_request_id(request),
    )
