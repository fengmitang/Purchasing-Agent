"""Request-scoped correlation context."""

from contextvars import ContextVar, Token

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the request ID for the current execution context."""
    return _request_id.get()


def set_request_id(request_id: str) -> Token[str]:
    """Set a request ID and return a token that can restore prior context."""
    return _request_id.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    """Restore the request context represented by ``token``."""
    _request_id.reset(token)
