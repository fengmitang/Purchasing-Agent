import sys
import types
import unittest
from unittest.mock import patch

try:
    import httpx  # noqa: F401
except ModuleNotFoundError:
    httpx_stub = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    httpx_stub.HTTPError = HTTPError
    httpx_stub.AsyncClient = object
    sys.modules["httpx"] = httpx_stub

from app.modules.agent.procurement.backend_client import (
    ProcurementBackendClient,
    ProcurementBackendError,
)
from app.modules.agent.procurement.idempotency import update_idempotency_key

DETAIL = {
    "requirement_id": 501,
    "requirement_no": "PR-20260721-0501",
    "status": "DRAFT",
    "version": 1,
    "quantity": "2.0000",
    "unit_price": "18500.00",
    "total_amount": "37000.00",
    "currency": "CNY",
    "missing_fields": [],
    "conflicts": [],
    "warnings": [],
}

SUBMISSION = {
    "requirement_id": 501,
    "requirement_no": "PR-20260721-0501",
    "status": "PENDING_APPROVAL",
    "version": 2,
    "submitted_at": "2026-07-22T08:00:00Z",
}


class FakeResponse:
    def __init__(self, status_code=200, body=None, invalid_json=False):
        self.status_code = status_code
        self._body = body
        self._invalid_json = invalid_json

    @property
    def is_error(self):
        return self.status_code >= 400

    def json(self):
        if self._invalid_json:
            raise ValueError("not json")
        return self._body


class FakeAsyncClient:
    response = FakeResponse(body={"data": DETAIL, "meta": {}})
    error = None
    calls = []
    options = []

    def __init__(self, **kwargs):
        type(self).options.append(kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method, path, **kwargs):
        type(self).calls.append((method, path, kwargs))
        if type(self).error:
            raise type(self).error
        return type(self).response

    @classmethod
    def reset(cls):
        cls.response = FakeResponse(body={"data": DETAIL, "meta": {}})
        cls.error = None
        cls.calls = []
        cls.options = []


class ProcurementBackendContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeAsyncClient.reset()
        self.patcher = patch(
            "app.modules.agent.procurement.backend_client.httpx.AsyncClient",
            FakeAsyncClient,
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    async def test_post_contract_headers_body_and_decimal_strings(self):
        client = ProcurementBackendClient("https://backend.test", service_token="service-token")
        result = await client.create_draft(
            {"session_id": "conv-1", "quantity": "2.0000", "unit_price": "18500.00"},
            authorization="Bearer user-token",
            request_id="request-1",
            idempotency_key="create-key",
        )
        method, path, kwargs = FakeAsyncClient.calls[0]
        self.assertEqual(("POST", "/api/v1/purchase-requirements/drafts"), (method, path))
        self.assertEqual("Bearer user-token", kwargs["headers"]["Authorization"])
        self.assertEqual("request-1", kwargs["headers"]["X-Request-ID"])
        self.assertEqual("create-key", kwargs["headers"]["Idempotency-Key"])
        self.assertEqual("2.0000", kwargs["json"]["quantity"])
        self.assertEqual("2.0000", result.quantity)
        self.assertEqual("18500.00", result.unit_price)

    async def test_get_has_correct_path_and_no_idempotency_header(self):
        client = ProcurementBackendClient("https://backend.test", service_token="service-token")
        await client.get_detail(501, authorization=None, request_id="request-2")
        method, path, kwargs = FakeAsyncClient.calls[0]
        self.assertEqual(("GET", "/api/v1/purchase-requirements/501"), (method, path))
        self.assertEqual("Bearer service-token", kwargs["headers"]["Authorization"])
        self.assertNotIn("Idempotency-Key", kwargs["headers"])

    async def test_patch_contract_includes_version_and_idempotency(self):
        client = ProcurementBackendClient("https://backend.test")
        await client.update_draft(
            501,
            {"version": 7, "application_reason": "扩容"},
            authorization="user-token",
            request_id="request-3",
            idempotency_key="draft-501-v7-hash",
        )
        method, path, kwargs = FakeAsyncClient.calls[0]
        self.assertEqual(("PATCH", "/api/v1/purchase-requirements/501"), (method, path))
        self.assertEqual(7, kwargs["json"]["version"])
        self.assertEqual("Bearer user-token", kwargs["headers"]["Authorization"])
        self.assertEqual("draft-501-v7-hash", kwargs["headers"]["Idempotency-Key"])

    async def test_submit_contract_requires_confirmation_and_new_idempotency_key(self):
        FakeAsyncClient.response = FakeResponse(body={"data": SUBMISSION, "meta": {}})
        client = ProcurementBackendClient("https://backend.test")

        result = await client.submit(
            501,
            {"version": 1, "confirmed": True, "recommendation_id": None},
            authorization="user-token",
            request_id="request-submit",
            idempotency_key="submit-501-v1",
        )

        method, path, kwargs = FakeAsyncClient.calls[0]
        self.assertEqual(
            ("POST", "/api/v1/purchase-requirements/501/submit"),
            (method, path),
        )
        self.assertIs(True, kwargs["json"]["confirmed"])
        self.assertEqual("submit-501-v1", kwargs["headers"]["Idempotency-Key"])
        self.assertEqual("PENDING_APPROVAL", result.status)

    def test_patch_idempotency_key_is_deterministic(self):
        first = update_idempotency_key(501, 7, {"quantity": "2", "unit": "台"})
        second = update_idempotency_key(501, 7, {"unit": "台", "quantity": "2"})
        self.assertEqual(first, second)

    async def test_mock_transport_is_injected(self):
        marker = object()
        client = ProcurementBackendClient("https://backend.test", transport=marker)
        await client.get_detail(501, authorization=None, request_id="request-4")
        self.assertIs(marker, FakeAsyncClient.options[0]["transport"])

    async def test_stable_backend_errors_are_preserved(self):
        for status, code in (
            (401, "UNAUTHENTICATED"),
            (403, "FORBIDDEN"),
            (404, "RESOURCE_NOT_FOUND"),
            (409, "VERSION_CONFLICT"),
            (422, "VALIDATION_ERROR"),
        ):
            with self.subTest(status=status):
                FakeAsyncClient.reset()
                FakeAsyncClient.response = FakeResponse(
                    status_code=status,
                    body={"error": {"code": code, "message": "failed", "details": []}},
                )
                with self.assertRaises(ProcurementBackendError) as caught:
                    await ProcurementBackendClient("https://backend.test").get_detail(
                        501, authorization=None, request_id="request-error"
                    )
                self.assertEqual(code, caught.exception.code)
                self.assertEqual(status, caught.exception.status_code)

    async def test_non_json_and_missing_data_are_invalid_responses(self):
        for response in (
            FakeResponse(body=None, invalid_json=True),
            FakeResponse(body={"meta": {}}),
        ):
            with self.subTest(response=response):
                FakeAsyncClient.reset()
                FakeAsyncClient.response = response
                with self.assertRaises(ProcurementBackendError) as caught:
                    await ProcurementBackendClient("https://backend.test").get_detail(
                        501, authorization=None, request_id="request-invalid"
                    )
                self.assertEqual("INVALID_BACKEND_RESPONSE", caught.exception.code)

    async def test_network_failure_is_backend_unavailable(self):
        from app.modules.agent.procurement import backend_client as backend_module

        FakeAsyncClient.error = backend_module.httpx.HTTPError("timeout")
        with self.assertRaises(ProcurementBackendError) as caught:
            await ProcurementBackendClient("https://backend.test").get_detail(
                501, authorization=None, request_id="request-timeout"
            )
        self.assertEqual("BACKEND_UNAVAILABLE", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
