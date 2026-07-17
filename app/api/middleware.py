"""HTTP middleware for request correlation and safe failure handling."""

import logging
import re
from time import perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.shared.errors import ErrorCode
from app.shared.request_context import reset_request_id, set_request_id
from app.shared.responses import error_json_response

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def resolve_request_id(candidate: str | None) -> str:
    """Accept a bounded safe caller ID or generate an opaque local ID."""
    if candidate and _SAFE_REQUEST_ID.fullmatch(candidate):
        return candidate
    return uuid4().hex


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Correlate requests, emit completion logs, and contain unknown failures."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started_at = perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception(
                    "Unhandled application error method=%s path=%s",
                    request.method,
                    request.url.path,
                )
                response = error_json_response(
                    status_code=500,
                    code=ErrorCode.INTERNAL_ERROR,
                    message="An internal error occurred",
                    request_id=request_id,
                )

            response.headers[REQUEST_ID_HEADER] = request_id
            elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
            logger.info(
                "Request completed method=%s path=%s status=%s duration_ms=%s",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            return response
        finally:
            reset_request_id(token)
