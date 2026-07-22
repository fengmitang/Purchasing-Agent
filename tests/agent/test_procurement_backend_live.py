import os
import unittest
import uuid

try:
    import httpx  # noqa: F401
except ModuleNotFoundError as exc:  # pragma: no cover - local minimal runtime
    raise unittest.SkipTest("httpx is required for live procurement tests") from exc

from app.modules.agent.procurement.backend_client import (
    ProcurementBackendClient,
    ProcurementBackendError,
)

LIVE_ENABLED = os.getenv("RUN_PROCUREMENT_LIVE_TESTS") == "1"
BASE_URL = os.getenv("PURCHASING_BACKEND_BASE_URL", "")
TOKEN = os.getenv("PURCHASING_BACKEND_TEST_TOKEN", "")


@unittest.skipUnless(
    LIVE_ENABLED and BASE_URL and TOKEN,
    "Set RUN_PROCUREMENT_LIVE_TESTS=1, PURCHASING_BACKEND_BASE_URL and test token",
)
class ProcurementBackendLiveTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = ProcurementBackendClient(BASE_URL)
        self.authorization = TOKEN if TOKEN.lower().startswith("bearer ") else f"Bearer {TOKEN}"

    async def test_draft_lifecycle_contract(self):
        suffix = uuid.uuid4().hex
        session_id = f"LIVE-TEST-{suffix}"
        create_key = f"live-create-{suffix}"
        payload = {
            "session_id": session_id,
            "product_name": "服务器",
            "quantity": "2",
            "unit": "台",
            "currency": "CNY",
        }
        created = await self.client.create_draft(
            payload,
            authorization=self.authorization,
            request_id=f"live-{suffix}-create",
            idempotency_key=create_key,
        )
        self.assertEqual("DRAFT", created.status)
        self.assertTrue(created.requirement_id)
        self.assertTrue(created.requirement_no)
        self.assertTrue(created.missing_fields)

        fetched = await self.client.get_detail(
            created.requirement_id,
            authorization=self.authorization,
            request_id=f"live-{suffix}-get",
        )
        self.assertEqual(created.requirement_id, fetched.requirement_id)

        updated = await self.client.update_draft(
            created.requirement_id,
            {
                "version": fetched.version,
                "application_reason": "LIVE TEST - capacity expansion",
                "application_location": "LIVE TEST building",
            },
            authorization=self.authorization,
            request_id=f"live-{suffix}-patch",
            idempotency_key=f"live-patch-{suffix}",
        )
        self.assertEqual(created.requirement_id, updated.requirement_id)
        self.assertGreater(updated.version, fetched.version)
        self.assertEqual("服务器", updated.product_name)

        with self.assertRaises(ProcurementBackendError) as stale:
            await self.client.update_draft(
                created.requirement_id,
                {"version": fetched.version, "application_reason": "stale write"},
                authorization=self.authorization,
                request_id=f"live-{suffix}-stale",
                idempotency_key=f"live-stale-{suffix}",
            )
        self.assertEqual("VERSION_CONFLICT", stale.exception.code)

        replay = await self.client.create_draft(
            payload,
            authorization=self.authorization,
            request_id=f"live-{suffix}-replay",
            idempotency_key=create_key,
        )
        self.assertEqual(created.requirement_id, replay.requirement_id)

        with self.assertRaises(ProcurementBackendError) as conflict:
            await self.client.create_draft(
                {**payload, "quantity": "3"},
                authorization=self.authorization,
                request_id=f"live-{suffix}-idempotency-conflict",
                idempotency_key=create_key,
            )
        self.assertEqual("IDEMPOTENCY_CONFLICT", conflict.exception.code)

    async def test_missing_identity_is_unauthenticated(self):
        with self.assertRaises(ProcurementBackendError) as caught:
            await self.client.get_detail(1, authorization=None, request_id="live-no-auth")
        self.assertEqual("UNAUTHENTICATED", caught.exception.code)

    async def test_other_user_cannot_read_draft(self):
        other_token = os.getenv("PURCHASING_BACKEND_OTHER_TEST_TOKEN", "")
        if not other_token:
            self.skipTest("PURCHASING_BACKEND_OTHER_TEST_TOKEN is not configured")
        suffix = uuid.uuid4().hex
        created = await self.client.create_draft(
            {
                "session_id": f"LIVE-TEST-{suffix}",
                "product_name": "服务器",
                "quantity": "2",
                "unit": "台",
                "currency": "CNY",
            },
            authorization=self.authorization,
            request_id=f"live-{suffix}-owner-create",
            idempotency_key=f"live-owner-{suffix}",
        )
        other_auth = (
            other_token if other_token.lower().startswith("bearer ") else f"Bearer {other_token}"
        )
        with self.assertRaises(ProcurementBackendError) as caught:
            await self.client.get_detail(
                created.requirement_id,
                authorization=other_auth,
                request_id=f"live-{suffix}-other-user",
            )
        self.assertIn(caught.exception.code, {"FORBIDDEN", "RESOURCE_NOT_FOUND"})


if __name__ == "__main__":
    unittest.main()
