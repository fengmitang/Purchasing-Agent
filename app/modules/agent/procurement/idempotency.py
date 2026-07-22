import hashlib
from typing import Any


def update_idempotency_key(
    requirement_id: int,
    version: int,
    patch: dict[str, Any],
) -> str:
    canonical = repr(sorted(patch.items())).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()[:16]
    return f"draft-{requirement_id}-v{version}-{digest}"
