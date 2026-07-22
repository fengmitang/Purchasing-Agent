from types import SimpleNamespace

import pytest

from app.modules.agent.procurement.backend_client import ProcurementBackendError
from app.modules.agent.procurement.service_backend import RequirementServiceBackend
from app.shared.identity import CurrentUser


def _detail() -> SimpleNamespace:
    payload = {
        "requirement_id": 7,
        "requirement_no": "PR-7",
        "status": "DRAFT",
        "version": 1,
        "currency": "CNY",
    }
    return SimpleNamespace(model_dump=lambda **_: payload)


class StubRequirementService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, object]] = []

    async def create_draft(self, command, context):
        self.calls.append(("create", command, context))
        return _detail()

    async def get_detail(self, requirement_id, actor):
        self.calls.append(("get", requirement_id, actor))
        return _detail()

    async def update_draft(self, requirement_id, command, context):
        self.calls.append(("update", requirement_id, context))
        assert command.version == 1
        return _detail()


@pytest.mark.asyncio
async def test_internal_backend_routes_writes_through_requirement_service() -> None:
    service = StubRequirementService()
    actor = CurrentUser(user_code="EMP-1")
    backend = RequirementServiceBackend(service)  # type: ignore[arg-type]

    created = await backend.create_draft(
        {"product_name": "server"},
        actor=actor,
        request_id="req-1",
        idempotency_key="idem-1",
    )
    updated = await backend.update_draft(
        7,
        {"version": 1, "quantity": "2"},
        actor=actor,
        request_id="req-2",
        idempotency_key="idem-2",
    )

    assert created.requirement_id == updated.requirement_id == 7
    assert service.calls[0][2].actor == actor
    assert service.calls[0][2].idempotency_key == "idem-1"
    assert service.calls[1][2].idempotency_key == "idem-2"


@pytest.mark.asyncio
async def test_internal_backend_forwards_trusted_actor_to_reads() -> None:
    service = StubRequirementService()
    actor = CurrentUser(user_code="EMP-2")
    backend = RequirementServiceBackend(service)  # type: ignore[arg-type]

    detail = await backend.get_detail(7, actor=actor, request_id="req-1")

    assert detail.requirement_id == 7
    assert service.calls == [("get", 7, actor)]


@pytest.mark.asyncio
async def test_internal_backend_returns_safe_error_for_invalid_tool_payload() -> None:
    service = StubRequirementService()
    backend = RequirementServiceBackend(service)  # type: ignore[arg-type]

    with pytest.raises(ProcurementBackendError) as caught:
        await backend.create_draft(
            {"product_name": "server", "currency": "yuan"},
            actor=CurrentUser(user_code="EMP-3"),
            request_id="req-invalid",
            idempotency_key="idem-invalid",
        )

    assert caught.value.code == "VALIDATION_ERROR"
    assert caught.value.status_code == 422
    assert caught.value.details == [{"field": "currency", "reason": "string_pattern_mismatch"}]
    assert service.calls == []
