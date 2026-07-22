from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_requirement_service
from app.bootstrap import create_application
from app.modules.requirement.schemas import (
    ApplicantSnapshot,
    HistoricalPurchaseSummary,
    HistoricalSupplierRecommendation,
    HistoricalSupplierRecommendationResult,
    RequirementDetail,
    RequirementNotice,
    RequirementSubmissionResult,
    RequirementSummary,
)
from app.shared.identity import CurrentUser


def requirement_detail(*, version: int = 1) -> RequirementDetail:
    now = datetime(2026, 7, 21, 6, 30, tzinfo=UTC)
    return RequirementDetail(
        requirement_id=501,
        requirement_no="PR-20260721-0501",
        status="DRAFT",
        version=version,
        applicant=ApplicantSnapshot(employee_no="E20260001", name="测试员工", phone=None),
        session_id="session-001",
        category_id=None,
        category_name="服务器及配件",
        application_reason="测试环境扩容",
        application_location=None,
        device_type="服务器",
        product_id=None,
        product_name="机架式服务器",
        product_full_name=None,
        brand=None,
        model=None,
        specification=None,
        quantity=Decimal("2.0000"),
        unit="台",
        supplier_id=None,
        supplier_name="新测试供应商",
        unit_price=Decimal("35000.00"),
        total_amount=Decimal("70000.00"),
        currency="CNY",
        new_product=True,
        new_supplier=True,
        missing_fields=["application_location"],
        conflicts=[],
        warnings=[
            RequirementNotice(
                code="SUPPLIER_NOT_IN_MASTER_DATA",
                message="该供应商尚未进入供应商主数据，提交后由采购人员核实。",
            )
        ],
        requested_at=now,
        submitted_at=None,
        updated_at=now,
    )


class StubRequirementService:
    def __init__(self) -> None:
        self.created = None
        self.updated = None

    async def create_draft(self, command, context):
        self.created = (command, context)
        return requirement_detail()

    async def get_detail(self, requirement_id, actor):
        assert requirement_id == 501
        assert actor.user_code == "E20260001"
        return requirement_detail()

    async def update_draft(self, requirement_id, command, context):
        self.updated = (requirement_id, command, context)
        return requirement_detail(version=command.version + 1)

    async def list_mine(self, *, actor, status, page, page_size):
        assert actor.user_code == "E20260001"
        assert (status, page, page_size) == ("DRAFT", 1, 20)
        return (
            [
                RequirementSummary(
                    requirement_id=501,
                    requirement_no="PR-20260721-0501",
                    product_name="机架式服务器",
                    status="DRAFT",
                    total_amount=Decimal("70000.00"),
                    currency="CNY",
                    updated_at=datetime(2026, 7, 21, 6, 30, tzinfo=UTC),
                    version=1,
                )
            ],
            1,
        )

    async def search_historical_suppliers(self, query, actor):
        assert query.requirement_id == 501
        assert actor.user_code == "E20260001"
        purchase = HistoricalPurchaseSummary(
            requirement_id=86,
            requirement_no="PR-HISTORY-86",
            order_id=31,
            order_no="PO-HISTORY-31",
            product_name="机架式服务器",
            brand="测试品牌",
            model="TEST-MODEL",
            quantity=Decimal("2.0000"),
            unit="台",
            unit_price=Decimal("34800.00"),
            currency="CNY",
            purchased_at=datetime(2026, 3, 20, tzinfo=UTC),
            received_at=datetime(2026, 4, 2, tzinfo=UTC),
            status="COMPLETED",
        )
        return HistoricalSupplierRecommendationResult(
            query_summary="机架式服务器 / 测试品牌 / TEST-MODEL",
            result_code="OK",
            recommendations=[
                HistoricalSupplierRecommendation(
                    rank=1,
                    match_score=Decimal("0.9200"),
                    matched_fields=["product_name", "brand", "model"],
                    supplier_id=12,
                    supplier_name="历史测试供应商",
                    historical_order_count=4,
                    latest_purchase=purchase,
                    reason="历史匹配",
                    warnings=["历史价格仅供参考，不代表当前报价。"],
                )
            ],
        )

    async def submit(self, requirement_id, command, context):
        assert requirement_id == 501
        assert command.confirmed is True
        return RequirementSubmissionResult(
            requirement_id=501,
            requirement_no="PR-20260721-0501",
            status="PENDING_APPROVAL",
            version=command.version + 1,
            submitted_at=datetime(2026, 7, 21, 7, 0, tzinfo=UTC),
        )

    async def cancel_draft(self, requirement_id, command, context):
        detail = requirement_detail(version=command.version + 1)
        return detail.model_copy(update={"status": "CANCELLED"})

    async def revise_rejected(self, requirement_id, command, context):
        assert requirement_id == 501
        assert command.version == 4
        assert context.idempotency_key == "revise-501"
        return requirement_detail().model_copy(
            update={
                "requirement_id": 502,
                "requirement_no": "PR-20260722-0502",
                "status": "DRAFT",
                "version": 1,
            }
        )


def build_client(service: StubRequirementService) -> TestClient:
    application = create_application()
    application.dependency_overrides[get_current_user] = lambda: CurrentUser(user_code="E20260001")
    application.dependency_overrides[get_requirement_service] = lambda: service
    return TestClient(application)


def test_create_draft_uses_contract_envelope_and_idempotency_key() -> None:
    service = StubRequirementService()
    client = build_client(service)

    response = client.post(
        "/api/v1/purchase-requirements/drafts",
        headers={"Idempotency-Key": "draft-create-1", "X-Request-ID": "draft-request-1"},
        json={
            "product_name": "机架式服务器",
            "quantity": "2",
            "unit": "台",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["quantity"] == "2"
    assert response.json()["data"]["total_amount"] == "70000.00"
    assert response.json()["meta"]["request_id"] == "draft-request-1"
    assert service.created[1].idempotency_key == "draft-create-1"


def test_get_detail_returns_database_backed_confirmation_view() -> None:
    response = build_client(StubRequirementService()).get(
        "/api/v1/purchase-requirements/501",
        headers={"X-Request-ID": "draft-get-1"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["requirement_no"] == "PR-20260721-0501"
    assert response.json()["data"]["missing_fields"] == ["application_location"]


def test_patch_passes_version_and_only_explicit_fields() -> None:
    service = StubRequirementService()
    response = build_client(service).patch(
        "/api/v1/purchase-requirements/501",
        headers={"Idempotency-Key": "draft-update-1"},
        json={"version": 3, "supplier_name": "员工选择的新供应商"},
    )

    assert response.status_code == 200
    command = service.updated[1]
    assert command.version == 3
    assert command.model_fields_set == {"version", "supplier_name"}
    assert response.json()["data"]["version"] == 4


def test_write_requires_idempotency_key() -> None:
    response = build_client(StubRequirementService()).post(
        "/api/v1/purchase-requirements/drafts",
        json={"product_name": "服务器"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_my_requirements_is_paginated() -> None:
    response = build_client(StubRequirementService()).get(
        "/api/v1/purchase-requirements?mine=true&status=DRAFT&page=1&page_size=20"
    )

    assert response.status_code == 200
    assert response.json()["data"][0]["total_amount"] == "70000.00"
    assert response.json()["page"] == {"number": 1, "size": 20, "total": 1}


def test_historical_supplier_search_returns_traceable_purchase() -> None:
    response = build_client(StubRequirementService()).post(
        "/api/v1/recommendations/historical-suppliers/search",
        json={"requirement_id": 501, "limit": 5},
    )

    assert response.status_code == 200
    recommendation = response.json()["data"]["recommendations"][0]
    assert recommendation["supplier_name"] == "历史测试供应商"
    assert recommendation["latest_purchase"]["order_no"] == "PO-HISTORY-31"
    assert recommendation["latest_purchase"]["unit_price"] == "34800.00"


def test_submit_and_cancel_require_explicit_confirmation() -> None:
    client = build_client(StubRequirementService())

    rejected = client.post(
        "/api/v1/purchase-requirements/501/submit",
        headers={"Idempotency-Key": "submit-1"},
        json={"version": 1, "confirmed": False},
    )
    submitted = client.post(
        "/api/v1/purchase-requirements/501/submit",
        headers={"Idempotency-Key": "submit-2"},
        json={"version": 1, "confirmed": True},
    )
    cancelled = client.post(
        "/api/v1/purchase-requirements/501/cancel",
        headers={"Idempotency-Key": "cancel-1"},
        json={"version": 1, "confirmed": True, "reason": "不再采购"},
    )

    assert rejected.status_code == 422
    assert submitted.status_code == 200
    assert submitted.json()["data"]["status"] == "PENDING_APPROVAL"
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"


def test_rejected_requirement_can_create_a_new_editable_draft() -> None:
    response = build_client(StubRequirementService()).post(
        "/api/v1/purchase-requirements/501/revise",
        headers={"Idempotency-Key": "revise-501"},
        json={"version": 4, "confirmed": True},
    )

    assert response.status_code == 201
    assert response.json()["data"]["requirement_id"] == 502
    assert response.json()["data"]["status"] == "DRAFT"
    assert response.json()["data"]["version"] == 1
