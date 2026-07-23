import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.config import Settings
from app.infrastructure.database import create_database_engine, create_session_factory
from app.modules.requirement.schemas import (
    CancelRequirementDraft,
    CreateRequirementDraft,
    HistoricalSupplierQuery,
    SubmitRequirement,
    UpdateRequirementDraft,
)
from app.modules.requirement.service import RequirementService
from app.shared.errors import DomainError, ErrorCode
from app.shared.identity import AuditContext, CurrentUser

pytestmark = pytest.mark.integration
_test_building_id: int | None = None


def require_test_database_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for MySQL integration tests")
    return database_url


async def clean_api_records(connection) -> None:
    await connection.execute(
        text(
            "DELETE history FROM purchase_status_history history "
            "JOIN purchase_requirement requirement "
            "ON history.requirement_id = requirement.id "
            "WHERE requirement.requirement_no LIKE 'API-REQ-%' "
            "OR requirement.requirement_no LIKE 'API-HISTORY-%'"
        )
    )
    await connection.execute(
        text(
            "DELETE recommendation FROM recommendation recommendation "
            "JOIN purchase_requirement requirement "
            "ON recommendation.requirement_id = requirement.id "
            "WHERE requirement.requirement_no LIKE 'API-REQ-%' "
            "OR requirement.requirement_no LIKE 'API-HISTORY-%'"
        )
    )
    await connection.execute(text("DELETE FROM purchase_order WHERE order_no LIKE 'API-ORDER-%'"))
    await connection.execute(text("DELETE FROM idempotency_record WHERE actor_code LIKE 'API-%'"))
    await connection.execute(
        text(
            "DELETE FROM purchase_requirement WHERE requirement_no LIKE 'API-REQ-%' "
            "OR requirement_no LIKE 'API-HISTORY-%'"
        )
    )
    await connection.execute(text("DELETE FROM employee WHERE employee_no LIKE 'API-%'"))
    await connection.execute(
        text(
            "DELETE relation FROM product_supplier relation "
            "JOIN product_whitelist product ON relation.product_id = product.id "
            "WHERE product.product_name = 'API历史服务器'"
        )
    )
    await connection.execute(
        text("DELETE FROM product_whitelist WHERE product_name = 'API历史服务器'")
    )
    await connection.execute(text("DELETE FROM supplier WHERE supplier_name = 'API历史供应商'"))
    await connection.execute(text("DELETE FROM product_category WHERE name = 'API测试分类'"))
    await connection.execute(text("DELETE FROM building WHERE building_code = 'API-BUILDING'"))


@pytest_asyncio.fixture
async def service() -> AsyncIterator[RequirementService]:
    global _test_building_id
    database_url = require_test_database_url()
    os.environ["DATABASE_URL"] = database_url
    await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "head")
    engine = create_database_engine(Settings(database_url=database_url, _env_file=None))
    async with engine.begin() as connection:
        await clean_api_records(connection)
        await connection.execute(
            text(
                "INSERT INTO employee (employee_no, name, phone, role, status) VALUES "
                "('API-E001', '接口测试员工一', '13900000001', 'EMPLOYEE', 'ACTIVE'), "
                "('API-E002', '接口测试员工二', '13900000002', 'EMPLOYEE', 'ACTIVE'), "
                "('API-HIST', '历史测试员工', '13900000003', 'EMPLOYEE', 'ACTIVE')"
            )
        )
        building_result = await connection.execute(
            text(
                "INSERT INTO building (building_code, building_name, status, version) "
                "VALUES ('API-BUILDING', '接口测试楼宇', 'ACTIVE', 1)"
            )
        )
        _test_building_id = int(building_result.lastrowid)
        category_result = await connection.execute(
            text("INSERT INTO product_category (name) VALUES ('API测试分类')")
        )
        category_id = category_result.lastrowid
        product_result = await connection.execute(
            text(
                "INSERT INTO product_whitelist "
                "(category_id, product_name, brand, model, specification, unit, status) "
                "VALUES (:category_id, 'API历史服务器', 'API品牌', 'API-MODEL-1', "
                "'2U双路测试配置', '台', 'ACTIVE')"
            ),
            {"category_id": category_id},
        )
        product_id = product_result.lastrowid
        supplier_result = await connection.execute(
            text("INSERT INTO supplier (supplier_name, status) VALUES ('API历史供应商', 'ACTIVE')")
        )
        supplier_id = supplier_result.lastrowid
        historical_employee_id = await connection.scalar(
            text("SELECT id FROM employee WHERE employee_no = 'API-HIST'")
        )
        requirement_result = await connection.execute(
            text(
                "INSERT INTO purchase_requirement ("
                "requirement_no, employee_id, applicant_employee_no, applicant_name, "
                "requested_at, submitted_at, category_id, category_name, application_reason, "
                "application_location, device_type, product_id, product_name, product_full_name, "
                "brand, model, specification, quantity, unit, supplier_id, supplier_name, "
                "unit_price, total_amount, currency, status, updated_at, version"
                ") VALUES ("
                "'API-HISTORY-001', :employee_id, 'API-HIST', '历史测试员工', "
                "'2026-03-01 08:00:00', '2026-03-01 09:00:00', :category_id, 'API测试分类', "
                "'历史扩容采购', 'A区数据中心', '服务器', :product_id, 'API历史服务器', "
                "'API品牌 API-MODEL-1 机架式服务器', 'API品牌', 'API-MODEL-1', "
                "'2U双路测试配置', 2, '台', :supplier_id, 'API历史供应商', 30000, 60000, "
                "'CNY', 'COMPLETED', '2026-03-20 08:00:00', 1)"
            ),
            {
                "employee_id": historical_employee_id,
                "category_id": category_id,
                "product_id": product_id,
                "supplier_id": supplier_id,
            },
        )
        historical_requirement_id = requirement_result.lastrowid
        await connection.execute(
            text(
                "INSERT INTO purchase_order ("
                "order_no, requirement_id, product_id, supplier_id, supplier_name, quantity, "
                "unit_price, amount, status, received_at"
                ") VALUES ("
                "'API-ORDER-001', :requirement_id, :product_id, :supplier_id, "
                "'API历史供应商', 2, 30000, 60000, 'COMPLETED', '2026-03-20 08:00:00')"
            ),
            {
                "requirement_id": historical_requirement_id,
                "product_id": product_id,
                "supplier_id": supplier_id,
            },
        )

    requirement_service = RequirementService(
        create_session_factory(engine),
        clock=lambda: datetime(2026, 7, 21, 8, 0, tzinfo=UTC),
        number_factory=lambda _now: f"API-REQ-{uuid4().hex[:16]}",
    )
    yield requirement_service

    async with engine.begin() as connection:
        await clean_api_records(connection)
    _test_building_id = None
    await engine.dispose()


def context(employee_no: str, key: str) -> AuditContext:
    assert _test_building_id is not None
    return AuditContext(
        actor=CurrentUser(
            user_code=employee_no,
            building_ids=frozenset({_test_building_id}),
        ),
        request_id=f"request-{key}",
        idempotency_key=key,
    )


@pytest.mark.asyncio
async def test_incomplete_draft_is_persisted_and_idempotent(
    service: RequirementService,
) -> None:
    command_payload = CreateRequirementDraft()

    first = await service.create_draft(command_payload, context("API-E001", "create-1"))
    replay = await service.create_draft(command_payload, context("API-E001", "create-1"))

    assert first.requirement_id == replay.requirement_id
    assert first.status == "DRAFT"
    assert first.applicant.employee_no == "API-E001"
    assert first.requested_at == datetime(2026, 7, 21, 8, 0, tzinfo=UTC)
    assert "product_name" in first.missing_fields
    assert "application_reason" in first.missing_fields

    with pytest.raises(DomainError) as captured:
        await service.create_draft(
            CreateRequirementDraft(product_name="不同内容"),
            context("API-E001", "create-1"),
        )
    assert captured.value.code is ErrorCode.IDEMPOTENCY_CONFLICT


@pytest.mark.asyncio
async def test_update_calculates_total_and_accepts_new_supplier(
    service: RequirementService,
) -> None:
    created = await service.create_draft(
        CreateRequirementDraft(product_name="机架式服务器", quantity="2.0000", unit="台"),
        context("API-E001", "create-2"),
    )

    updated = await service.update_draft(
        created.requirement_id,
        UpdateRequirementDraft(
            version=created.version,
            supplier_name="数据库中不存在的测试供应商",
            unit_price="35000.00",
        ),
        context("API-E001", "update-2"),
    )

    assert updated.version == 2
    assert updated.total_amount is not None
    assert format(updated.total_amount, ".2f") == "70000.00"
    assert updated.supplier_id is None
    assert updated.new_supplier is True
    assert {warning.code for warning in updated.warnings} == {
        "PRODUCT_NOT_IN_MASTER_DATA",
        "SUPPLIER_NOT_IN_MASTER_DATA",
    }


@pytest.mark.asyncio
async def test_stale_version_and_other_employee_are_rejected(
    service: RequirementService,
) -> None:
    created = await service.create_draft(
        CreateRequirementDraft(product_name="网络交换机"),
        context("API-E001", "create-3"),
    )

    with pytest.raises(DomainError) as stale:
        await service.update_draft(
            created.requirement_id,
            UpdateRequirementDraft(version=99, brand="测试品牌"),
            context("API-E001", "update-stale"),
        )
    assert stale.value.code is ErrorCode.VERSION_CONFLICT

    with pytest.raises(DomainError) as forbidden:
        await service.get_detail(created.requirement_id, CurrentUser(user_code="API-E002"))
    assert forbidden.value.code is ErrorCode.FORBIDDEN


@pytest.mark.asyncio
async def test_invalid_master_reference_rolls_back(service: RequirementService) -> None:
    with pytest.raises(DomainError) as captured:
        await service.create_draft(
            CreateRequirementDraft(product_id=999999999),
            context("API-E001", "invalid-product"),
        )

    assert captured.value.code is ErrorCode.RESOURCE_NOT_FOUND


@pytest.mark.asyncio
async def test_historical_supplier_recommendation_uses_completed_purchase(
    service: RequirementService,
) -> None:
    created = await service.create_draft(
        CreateRequirementDraft(
            category_name="算力服务器",
            application_reason="新增测试环境服务器",
            application_location="A区数据中心",
            device_type="服务器",
            product_name="API历史服务器",
            product_full_name="API品牌 API-MODEL-1 机架式服务器",
            brand="API品牌",
            model="API-MODEL-1",
            quantity="1.0000",
            unit="台",
        ),
        context("API-E001", "history-create"),
    )

    result = await service.search_historical_suppliers(
        HistoricalSupplierQuery(requirement_id=created.requirement_id, limit=5),
        CurrentUser(user_code="API-E001"),
    )

    assert result.result_code == "OK"
    assert result.recommendations[0].supplier_name == "API历史供应商"
    assert result.recommendations[0].latest_purchase.order_no == "API-ORDER-001"
    assert result.recommendations[0].latest_purchase.unit_price is not None
    assert format(result.recommendations[0].latest_purchase.unit_price, ".2f") == "30000.00"
    assert "历史价格仅供参考" in result.recommendations[0].warnings[0]


@pytest.mark.asyncio
async def test_confirmed_complete_draft_is_submitted_idempotently(
    service: RequirementService,
) -> None:
    created = await service.create_draft(
        CreateRequirementDraft(
            application_reason="测试环境扩容",
            application_location="A区数据中心",
            product_name="机架式服务器",
            quantity="2",
        ),
        context("API-E001", "submit-create"),
    )
    assert created.building_id == _test_building_id
    command_payload = SubmitRequirement(version=created.version, confirmed=True)

    submitted = await service.submit(
        created.requirement_id,
        command_payload,
        context("API-E001", "submit-action"),
    )
    replay = await service.submit(
        created.requirement_id,
        command_payload,
        context("API-E001", "submit-action"),
    )
    detail = await service.get_detail(
        created.requirement_id,
        CurrentUser(user_code="API-E001"),
    )

    assert submitted == replay
    assert submitted.status == "PENDING_APPROVAL"
    assert submitted.version == 2
    assert submitted.submitted_at == datetime(2026, 7, 21, 8, 0, tzinfo=UTC)
    assert detail.status == "PENDING_APPROVAL"
    assert detail.total_amount is None

    with pytest.raises(DomainError) as conflict:
        await service.update_draft(
            created.requirement_id,
            UpdateRequirementDraft(version=2, brand="不能再修改"),
            context("API-E001", "update-after-submit"),
        )
    assert conflict.value.code is ErrorCode.STATE_CONFLICT


@pytest.mark.asyncio
async def test_incomplete_submission_is_rejected_without_state_change(
    service: RequirementService,
) -> None:
    created = await service.create_draft(
        CreateRequirementDraft(product_name="信息不完整的设备"),
        context("API-E001", "incomplete-create"),
    )

    with pytest.raises(DomainError) as captured:
        await service.submit(
            created.requirement_id,
            SubmitRequirement(version=created.version, confirmed=True),
            context("API-E001", "incomplete-submit"),
        )

    assert captured.value.code is ErrorCode.REQUIREMENT_INCOMPLETE
    detail = await service.get_detail(created.requirement_id, CurrentUser(user_code="API-E001"))
    assert detail.status == "DRAFT"
    assert detail.version == 1


@pytest.mark.asyncio
async def test_cancel_and_list_only_current_employee_requirements(
    service: RequirementService,
) -> None:
    own = await service.create_draft(
        CreateRequirementDraft(product_name="待取消设备"),
        context("API-E001", "cancel-own"),
    )
    await service.create_draft(
        CreateRequirementDraft(product_name="其他员工设备"),
        context("API-E002", "cancel-other"),
    )

    cancelled = await service.cancel_draft(
        own.requirement_id,
        CancelRequirementDraft(version=own.version, confirmed=True, reason="需求取消"),
        context("API-E001", "cancel-action"),
    )
    requirements, total = await service.list_mine(
        actor=CurrentUser(user_code="API-E001"),
        status="CANCELLED",
        page=1,
        page_size=20,
    )

    assert cancelled.status == "CANCELLED"
    assert total == 1
    assert [item.requirement_id for item in requirements] == [own.requirement_id]
