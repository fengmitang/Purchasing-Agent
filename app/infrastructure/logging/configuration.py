"""Structured application logging with request correlation and redaction."""

import json
import logging
from datetime import UTC, datetime

from app.infrastructure.logging.redaction import redact
from app.shared.request_context import get_request_id


class RedactingJsonFormatter(logging.Formatter):
    """Emit structured JSON after sanitizing messages and exception text."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
            "request_id": getattr(record, "request_id", get_request_id()),
        }
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class RequestIdFilter(logging.Filter):
    """Attach the current request ID to every emitted record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure the process root logger using the shared safe formatter."""
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingJsonFormatter())
    handler.addFilter(RequestIdFilter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
