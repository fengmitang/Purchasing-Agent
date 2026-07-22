"""In-memory backend used only for manual procurement_agent integration testing."""

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse

app = FastAPI(title="procurement_agent backend mock")

_drafts: dict[int, dict[str, Any]] = {}
_idempotency: dict[str, tuple[str, int]] = {}
_next_id = 1000

_required_fields = (
    "product_name",
    "quantity",
    "unit",
    "application_reason",
    "application_location",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _missing(draft: dict[str, Any]) -> list[str]:
    return [name for name in _required_fields if draft.get(name) in (None, "")]


def _total(draft: dict[str, Any]) -> str | None:
    try:
        if draft.get("quantity") is None or draft.get("unit_price") is None:
            return None
        return str(Decimal(str(draft["quantity"])) * Decimal(str(draft["unit_price"])))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _detail(draft: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(draft)
    result["missing_fields"] = _missing(result)
    result["conflicts"] = []
    result["warnings"] = []
    result["total_amount"] = _total(result)
    return result


def _envelope(data: dict[str, Any], request_id: str | None) -> dict[str, Any]:
    return {"data": _detail(data), "meta": {"request_id": request_id}}


def _error(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": []}},
    )


@app.post("/api/v1/purchase-requirements/drafts", status_code=201)
async def create_draft(
    payload: dict[str, Any],
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    global _next_id
    canonical = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    if idempotency_key and idempotency_key in _idempotency:
        previous_hash, requirement_id = _idempotency[idempotency_key]
        if previous_hash != canonical:
            return _error("IDEMPOTENCY_CONFLICT", "Idempotency key payload conflict", 409)
        return _envelope(_drafts[requirement_id], x_request_id)

    _next_id += 1
    requirement_id = _next_id
    now = _now()
    draft = {
        "requirement_id": requirement_id,
        "requirement_no": f"MOCK-PR-{requirement_id}",
        "status": "DRAFT",
        "version": 1,
        "currency": "CNY",
        "new_product": False,
        "new_supplier": False,
        "applicant": {"display_name": (authorization or "mock-user").removeprefix("Bearer ")},
        "requested_at": now,
        "updated_at": now,
        **payload,
    }
    _drafts[requirement_id] = draft
    if idempotency_key:
        _idempotency[idempotency_key] = (canonical, requirement_id)
    return _envelope(draft, x_request_id)


@app.get("/api/v1/purchase-requirements/{requirement_id}")
async def get_detail(
    requirement_id: int,
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
):
    draft = _drafts.get(requirement_id)
    if draft is None:
        return _error("RESOURCE_NOT_FOUND", "Draft not found", 404)
    return _envelope(draft, x_request_id)


@app.patch("/api/v1/purchase-requirements/{requirement_id}")
async def update_draft(
    requirement_id: int,
    payload: dict[str, Any],
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
):
    draft = _drafts.get(requirement_id)
    if draft is None:
        return _error("RESOURCE_NOT_FOUND", "Draft not found", 404)
    if payload.get("version") != draft["version"]:
        return _error("VERSION_CONFLICT", "Draft version conflict", 409)
    if draft["status"] != "DRAFT":
        return _error("STATE_CONFLICT", "Only DRAFT can be updated", 409)

    for key, value in payload.items():
        if key != "version":
            draft[key] = value
    draft["version"] += 1
    draft["updated_at"] = _now()
    return _envelope(draft, x_request_id)


@app.get("/health")
async def health():
    return {"status": "ok", "draft_count": len(_drafts)}
