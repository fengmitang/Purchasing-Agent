from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_workflow_service
from app.bootstrap import create_application
from app.modules.workflow.schemas import (
    ApprovalDecisionResult,
    ApprovalTaskView,
    BuildingOption,
    ProcurementTaskView,
    WorkflowApplicant,
)
from app.shared.identity import CurrentUser

NOW = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)


def approval_task() -> ApprovalTaskView:
    return ApprovalTaskView(
        requirement_id=101,
        requirement_no="PR-20260722-0101",
        status="PENDING_APPROVAL",
        version=2,
        revision_no=1,
        building_id=1,
        building_name="A1 数据中心",
        applicant=WorkflowApplicant(
            employee_id=11, employee_no="DEV-E0001", name="测试员工", phone="13800000001"
        ),
        category_name="算力服务器",
        application_reason="测试环境扩容",
        application_location="A1 数据中心 3 楼",
        device_type="服务器",
        product_name="机架式服务器",
        product_full_name="双路机架式服务器",
        brand="测试品牌",
        model="TEST-2U",
        specification="2U 双路",
        quantity=Decimal("2"),
        unit="台",
        supplier_name="测试供应商",
        unit_price=Decimal("35000"),
        total_amount=Decimal("70000"),
        currency="CNY",
        submitted_at=NOW,
        updated_at=NOW,
    )


def procurement_task(
    *, status: str = "APPROVED", order_id: int | None = None
) -> ProcurementTaskView:
    return ProcurementTaskView(
        requirement_id=101,
        requirement_no="PR-20260722-0101",
        status=status,
        requirement_version=3,
        building_id=1,
        building_name="A1 数据中心",
        applicant_name="测试员工",
        product_name="机架式服务器",
        product_full_name="双路机架式服务器",
        brand="测试品牌",
        model="TEST-2U",
        specification="2U 双路",
        quantity=Decimal("2"),
        unit="台",
        supplier_name="测试供应商",
        unit_price=Decimal("35000"),
        total_amount=Decimal("70000"),
        currency="CNY",
        order_id=order_id,
        order_no="PO-20260722-0101" if order_id else None,
        order_version=1 if order_id else None,
        purchaser_employee_no="DEV-P0001" if order_id else None,
        purchaser_name="测试采购员" if order_id else None,
        purchaser_phone="13800000003" if order_id else None,
        purchasing_started_at=NOW if order_id else None,
        quoted_at=None,
        contracted_at=None,
        received_at=None,
        completed_at=None,
        updated_at=NOW,
    )


class StubWorkflowService:
    async def list_buildings(self):
        return [BuildingOption(building_id=1, building_code="A1", building_name="A1 数据中心")]

    async def list_approval_tasks(self, actor, *, view, page, page_size):
        assert "BUILDING_MANAGER" in actor.roles
        assert view in {"pending", "history"}
        assert (page, page_size) == (1, 20)
        return [approval_task()], 1

    async def get_approval_task(self, requirement_id, actor):
        assert requirement_id == 101
        assert 1 in actor.building_ids
        return approval_task()

    async def decide(self, requirement_id, command, context):
        assert requirement_id == 101
        assert command.action == "APPROVED"
        assert context.idempotency_key == "approve-101"
        return ApprovalDecisionResult(
            requirement_id=101,
            requirement_no="PR-20260722-0101",
            status="APPROVED",
            version=3,
            acted_at=NOW,
        )

    async def list_procurement_tasks(self, actor, *, page, page_size):
        assert "PURCHASER" in actor.roles
        return [procurement_task()], 1

    async def start_procurement(self, requirement_id, command, context):
        assert requirement_id == 101
        assert command.version == 3
        return procurement_task(status="PURCHASING", order_id=301)

    async def advance_procurement(self, order_id, command, context):
        assert order_id == 301
        assert command.target_status == "QUOTED"
        return procurement_task(status="QUOTED", order_id=301)

    async def complete_procurement(self, order_id, command, context):
        assert order_id == 301
        return procurement_task(status="COMPLETED", order_id=301).model_copy(
            update={"received_at": NOW, "completed_at": NOW}
        )

    async def rollback_procurement(self, order_id, command, context):
        assert order_id == 301
        assert command.version == 1
        return procurement_task(status="CONTRACTED", order_id=301)


def client_for(user: CurrentUser) -> TestClient:
    application = create_application()
    application.dependency_overrides[get_current_user] = lambda: user
    application.dependency_overrides[get_workflow_service] = lambda: StubWorkflowService()
    return TestClient(application)


def test_manager_can_list_open_and_approve_tasks() -> None:
    client = client_for(
        CurrentUser(
            user_code="DEV-A0001",
            roles=frozenset({"EMPLOYEE", "BUILDING_MANAGER"}),
            building_ids=frozenset({1}),
        )
    )

    listed = client.get("/api/v1/approvals/tasks")
    detail = client.get("/api/v1/approvals/tasks/101")
    approved = client.post(
        "/api/v1/approvals/tasks/101/decision",
        headers={"Idempotency-Key": "approve-101"},
        json={"version": 2, "action": "APPROVED", "comment": "同意采购"},
    )

    assert listed.status_code == 200
    assert listed.json()["page"]["total"] == 1
    assert detail.json()["data"]["building_name"] == "A1 数据中心"
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "APPROVED"


def test_manager_can_query_own_approval_history() -> None:
    client = client_for(
        CurrentUser(
            user_code="DEV-A0001",
            roles=frozenset({"EMPLOYEE", "BUILDING_MANAGER"}),
            employee_id=61,
            building_ids=frozenset({1}),
        )
    )

    response = client.get("/api/v1/approvals/tasks?view=history")

    assert response.status_code == 200
    assert response.json()["page"]["total"] == 1


def test_purchaser_can_move_task_through_key_nodes() -> None:
    client = client_for(
        CurrentUser(user_code="DEV-P0001", roles=frozenset({"EMPLOYEE", "PURCHASER"}))
    )

    listed = client.get("/api/v1/procurement/tasks")
    started = client.post(
        "/api/v1/procurement/requirements/101/start",
        headers={"Idempotency-Key": "start-101"},
        json={"version": 3},
    )
    quoted = client.post(
        "/api/v1/procurement/orders/301/advance",
        headers={"Idempotency-Key": "quote-301"},
        json={"version": 1, "target_status": "QUOTED"},
    )
    completed = client.post(
        "/api/v1/procurement/orders/301/complete",
        headers={"Idempotency-Key": "complete-301"},
        json={"version": 1, "remark": "验收合格"},
    )
    rolled_back = client.post(
        "/api/v1/procurement/orders/301/rollback",
        headers={"Idempotency-Key": "rollback-301"},
        json={"version": 1},
    )

    assert listed.status_code == 200
    assert started.json()["data"]["status"] == "PURCHASING"
    assert quoted.json()["data"]["status"] == "QUOTED"
    assert completed.json()["data"]["status"] == "COMPLETED"
    assert completed.json()["data"]["received_at"] is not None
    assert rolled_back.json()["data"]["status"] == "CONTRACTED"


def test_building_options_require_login() -> None:
    application = create_application()
    response = TestClient(application).get("/api/v1/buildings")
    assert response.status_code == 401
