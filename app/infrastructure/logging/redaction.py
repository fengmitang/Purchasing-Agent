"""Defense-in-depth redaction for log output."""

import re

REDACTED = "[REDACTED]"

_BEARER_PATTERN = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+")
_URL_CREDENTIAL_PATTERN = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)([^\s:/@]+):([^\s/@]+)@")
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(\b(?:password|passwd|token|secret|authorization|api[_-]?key|database_url)\b"
    r"\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)


def redact(value: object) -> str:
    """Return text with common credential shapes removed."""
    text = str(value)
    text = _BEARER_PATTERN.sub(rf"\1{REDACTED}", text)
    text = _URL_CREDENTIAL_PATTERN.sub(rf"\1{REDACTED}:{REDACTED}@", text)
    return _SENSITIVE_ASSIGNMENT_PATTERN.sub(rf"\1{REDACTED}", text)
