"""Stable public error codes and domain exceptions."""

from collections.abc import Sequence
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Error identifiers that form part of the public API contract."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    STATE_CONFLICT = "STATE_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    EMPLOYEE_NOT_MAPPED = "EMPLOYEE_NOT_MAPPED"
    REQUIREMENT_INCOMPLETE = "REQUIREMENT_INCOMPLETE"
    BLACKLIST_BLOCKED = "BLACKLIST_BLOCKED"
    RATE_LIMITED = "RATE_LIMITED"
    AGENT_UNAVAILABLE = "AGENT_UNAVAILABLE"
    CONVERSATION_BUSY = "CONVERSATION_BUSY"
    INTERNAL_ERROR = "INTERNAL_ERROR"


HTTP_STATUS_BY_ERROR_CODE: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.RESOURCE_NOT_FOUND: 404,
    ErrorCode.STATE_CONFLICT: 409,
    ErrorCode.IDEMPOTENCY_CONFLICT: 409,
    ErrorCode.VERSION_CONFLICT: 409,
    ErrorCode.EMPLOYEE_NOT_MAPPED: 422,
    ErrorCode.REQUIREMENT_INCOMPLETE: 422,
    ErrorCode.BLACKLIST_BLOCKED: 422,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.AGENT_UNAVAILABLE: 503,
    ErrorCode.CONVERSATION_BUSY: 409,
    ErrorCode.INTERNAL_ERROR: 500,
}


class DomainError(Exception):
    """A safe, expected business failure mapped to a stable API error."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Sequence[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = list(details or ())
