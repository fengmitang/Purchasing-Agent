import json
import logging
import re
from io import StringIO

from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.bootstrap import create_application
from app.infrastructure.logging.configuration import RedactingJsonFormatter
from app.shared.errors import DomainError, ErrorCode
from app.shared.responses import ResponseMeta, SuccessResponse


class ExampleInput(BaseModel):
    quantity: int = Field(gt=0)


def build_contract_client() -> TestClient:
    application = create_application()

    @application.post("/_test/validation")
    def validate_payload(payload: ExampleInput) -> dict[str, int]:
        return {"quantity": payload.quantity}

    @application.get("/_test/domain-error")
    def raise_domain_error() -> None:
        raise DomainError(ErrorCode.STATE_CONFLICT, "The resource state has changed")

    @application.get("/_test/unknown-error")
    def raise_unknown_error() -> None:
        raise RuntimeError("password=should-not-leak token=private-token")

    return TestClient(application)


def test_request_id_is_preserved_in_header_and_error_body() -> None:
    client = build_contract_client()

    response = client.get("/missing", headers={"X-Request-ID": "caller-123"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "caller-123"
    assert response.json() == {
        "error": {
            "code": "RESOURCE_NOT_FOUND",
            "message": "Resource not found",
            "details": [],
            "request_id": "caller-123",
        }
    }


def test_missing_or_invalid_request_id_is_replaced() -> None:
    client = build_contract_client()

    missing = client.get("/health")
    invalid = client.get("/health", headers={"X-Request-ID": "unsafe request id"})

    for response in (missing, invalid):
        request_id = response.headers["X-Request-ID"]
        assert re.fullmatch(r"[0-9a-f]{32}", request_id)
        assert set(response.json()) == {"status", "service", "version", "time"}


def test_validation_error_is_safe_and_stable() -> None:
    client = build_contract_client()

    response = client.post(
        "/_test/validation",
        json={"quantity": -1, "password": "must-not-be-echoed"},
        headers={"X-Request-ID": "validation-1"},
    )

    assert response.status_code == 422
    payload = response.json()["error"]
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["request_id"] == "validation-1"
    assert payload["details"][0]["location"] == ["body", "quantity"]
    assert "must-not-be-echoed" not in response.text


def test_domain_error_uses_documented_mapping() -> None:
    client = build_contract_client()

    response = client.get("/_test/domain-error")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_CONFLICT"
    assert response.json()["error"]["message"] == "The resource state has changed"


def test_unknown_error_returns_redacted_internal_response() -> None:
    client = build_contract_client()
    root_handler = logging.getLogger().handlers[0]
    original_stream = root_handler.stream
    stream = StringIO()
    root_handler.setStream(stream)
    try:
        response = client.get("/_test/unknown-error", headers={"X-Request-ID": "failure-1"})
    finally:
        root_handler.setStream(original_stream)

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "failure-1"
    assert response.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An internal error occurred",
            "details": [],
            "request_id": "failure-1",
        }
    }
    assert "should-not-leak" not in response.text
    assert "private-token" not in response.text
    assert "should-not-leak" not in stream.getvalue()
    assert "private-token" not in stream.getvalue()
    assert "[REDACTED]" in stream.getvalue()


def test_success_response_matches_documented_envelope() -> None:
    response = SuccessResponse[dict[str, str]](
        data={"result": "ok"},
        meta=ResponseMeta(request_id="success-1"),
    )

    assert response.model_dump(mode="json") == {
        "data": {"result": "ok"},
        "meta": {"request_id": "success-1"},
    }


def test_log_formatter_redacts_credentials_and_keeps_request_id() -> None:
    formatter = RedactingJsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=(
            "password=hunter2 authorization=Bearer abc.def "
            "database_url=mysql+asyncmy://user:db-secret@localhost/app"
        ),
        args=(),
        exc_info=None,
    )
    record.request_id = "log-123"

    payload = json.loads(formatter.format(record))

    assert payload["request_id"] == "log-123"
    assert payload["message"].count("[REDACTED]") >= 3
    assert "hunter2" not in payload["message"]
    assert "abc.def" not in payload["message"]
    assert "db-secret" not in payload["message"]


def test_request_id_is_in_request_completion_log() -> None:
    client = build_contract_client()
    root_handler = logging.getLogger().handlers[0]
    original_stream = root_handler.stream
    stream = StringIO()
    root_handler.setStream(stream)
    try:
        response = client.get("/health", headers={"X-Request-ID": "logged-request-1"})
    finally:
        root_handler.setStream(original_stream)

    assert response.status_code == 200
    entries = [json.loads(line) for line in stream.getvalue().splitlines()]
    completion = next(entry for entry in entries if entry["logger"] == "app.api.middleware")
    assert completion["request_id"] == "logged-request-1"
