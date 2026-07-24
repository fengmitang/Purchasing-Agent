"""采购申请草稿的业务规则与事务边界。"""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from pydantic import BaseModel

from app.infrastructure.database import AsyncSessionFactory, session_scope, transaction_scope
from app.modules.requirement.models import (
    Employee,
    IdempotencyRecord,
    PurchaseOrder,
    PurchaseRequirement,
    PurchaseStatusHistory,
)
from app.modules.requirement.repository import RequirementRepository
from app.modules.requirement.schemas import (
    ApplicantSnapshot,
    CancelRequirementDraft,
    CreateRequirementDraft,
    HistoricalPurchaseSummary,
    HistoricalSupplierQuery,
    HistoricalSupplierRecommendation,
    HistoricalSupplierRecommendationResult,
    RequirementDetail,
    RequirementNotice,
    RequirementSubmissionResult,
    RequirementSummary,
    ReviseRejectedRequirement,
    SubmitRequirement,
    UpdateRequirementDraft,
)
from app.shared.errors import DomainError, ErrorCode
from app.shared.identity import AuditContext, CurrentUser

_EDITABLE_FIELDS = {
    "session_id",
    "category_id",
    "application_reason",
    "application_location",
    "device_type",
    "product_id",
    "product_name",
    "product_full_name",
    "brand",
    "model",
    "specification",
    "quantity",
    "unit",
    "supplier_id",
    "supplier_name",
    "unit_price",
    "currency",
}
_REQUIRED_FOR_SUBMISSION = (
    "application_reason",
    "application_location",
    "product_name",
    "quantity",
)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _utc_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _request_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _clean_text(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


class RequirementService:
    """创建、读取和更新员工所属的采购申请草稿。"""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        clock: Callable[[], datetime] | None = None,
        number_factory: Callable[[datetime], str] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._number_factory = number_factory or self._default_requirement_number

    @staticmethod
    def _default_requirement_number(now: datetime) -> str:
        return f"PR-{now:%Y%m%d}-{uuid4().hex[:12].upper()}"

    async def create_draft(
        self,
        command: CreateRequirementDraft,
        context: AuditContext,
    ) -> RequirementDetail:
        """保存不完整草稿，但不提交审批。"""
        payload = command.model_dump(mode="json", exclude_unset=True)
        request_hash = _request_hash(payload)
        now_aware = self._clock()
        now = _utc_naive(now_aware)

        async with transaction_scope(self._session_factory) as session:
            repository = RequirementRepository(session)
            replay = await self._idempotent_replay(
                repository,
                actor_code=context.actor.user_code,
                operation="create_requirement_draft",
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if replay is not None:
                return replay

            employee = await self._require_employee(repository, context.actor)
            requirement = PurchaseRequirement(
                requirement_no=self._number_factory(now_aware),
                employee_id=employee.id,
                applicant_employee_no=employee.employee_no,
                applicant_name=employee.name,
                applicant_phone=employee.phone,
                requested_at=now,
                submitted_at=None,
                revision_no=1,
                previous_requirement_id=None,
                status="DRAFT",
                quantity_raw=None,
                unit_price_raw=None,
                source_reference=None,
                updated_at=now,
                version=1,
                total_amount=None,
                **self._draft_values(command),
            )
            await self._resolve_associations(
                repository,
                requirement,
                command.model_fields_set & _EDITABLE_FIELDS,
            )
            requirement.total_amount = self._calculate_total(
                requirement.quantity, requirement.unit_price
            )
            repository.add_requirement(requirement)
            await repository.flush()

            detail = self._to_detail(requirement, employee)
            repository.add_idempotency_record(
                self._idempotency_record(
                    context=context,
                    operation="create_requirement_draft",
                    request_hash=request_hash,
                    resource_id=requirement.id,
                    response=detail,
                    created_at=now,
                )
            )
            await repository.flush()
            return detail

    async def get_detail(
        self,
        requirement_id: int,
        actor: CurrentUser,
    ) -> RequirementDetail:
        """只向草稿所属员工返回数据库中的最新内容。"""
        async with session_scope(self._session_factory) as session:
            repository = RequirementRepository(session)
            employee = await self._require_employee(repository, actor)
            requirement = await repository.get_requirement(requirement_id)
            self._require_owned(requirement, employee)
            return self._to_detail(requirement, employee)

    async def update_draft(
        self,
        requirement_id: int,
        command: UpdateRequirementDraft,
        context: AuditContext,
    ) -> RequirementDetail:
        """校验状态、归属、版本和幂等后，对草稿执行部分更新。"""
        changed_fields = command.model_fields_set & _EDITABLE_FIELDS
        if not changed_fields:
            raise DomainError(
                ErrorCode.VALIDATION_ERROR,
                "请至少修改一项草稿内容",
                [{"field": "body", "reason": "empty_patch"}],
            )

        payload = command.model_dump(mode="json", exclude_unset=True)
        request_hash = _request_hash(payload)
        operation = f"update_requirement:{requirement_id}"
        now = _utc_naive(self._clock())

        async with transaction_scope(self._session_factory) as session:
            repository = RequirementRepository(session)
            replay = await self._idempotent_replay(
                repository,
                actor_code=context.actor.user_code,
                operation=operation,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if replay is not None:
                return replay

            employee = await self._require_employee(repository, context.actor)
            requirement = await repository.get_requirement_for_update(requirement_id)
            self._require_owned(requirement, employee)
            if requirement.status != "DRAFT":
                raise DomainError(
                    ErrorCode.STATE_CONFLICT,
                    "只有草稿状态的采购申请可以修改",
                    [{"status": requirement.status}],
                )
            if requirement.version != command.version:
                raise DomainError(
                    ErrorCode.VERSION_CONFLICT,
                    "采购申请已被其他请求更新，请刷新后重试",
                    [{"expected_version": command.version, "actual_version": requirement.version}],
                )

            for field in changed_fields:
                setattr(requirement, field, _clean_text(getattr(command, field)))
            await self._resolve_associations(repository, requirement, changed_fields)
            requirement.total_amount = self._calculate_total(
                requirement.quantity, requirement.unit_price
            )
            requirement.version += 1
            requirement.updated_at = now
            await repository.flush()

            detail = self._to_detail(requirement, employee)
            repository.add_idempotency_record(
                self._idempotency_record(
                    context=context,
                    operation=operation,
                    request_hash=request_hash,
                    resource_id=requirement.id,
                    response=detail,
                    created_at=now,
                )
            )
            await repository.flush()
            return detail

    async def list_mine(
        self,
        *,
        actor: CurrentUser,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[RequirementSummary], int]:
        """稳定分页查询当前已认证员工本人的采购申请。"""
        async with session_scope(self._session_factory) as session:
            repository = RequirementRepository(session)
            employee = await self._require_employee(repository, actor)
            requirements, total = await repository.list_owned_requirements(
                employee_id=employee.id,
                status=status,
                page=page,
                page_size=page_size,
            )
            return [self._to_summary(requirement) for requirement in requirements], total

    async def search_historical_suppliers(
        self,
        query: HistoricalSupplierQuery,
        actor: CurrentUser,
    ) -> HistoricalSupplierRecommendationResult:
        """根据与已保存草稿相似且可追溯的已完成采购记录排序供应商。"""
        async with session_scope(self._session_factory) as session:
            repository = RequirementRepository(session)
            employee = await self._require_employee(repository, actor)
            requirement = await repository.get_requirement(query.requirement_id)
            self._require_owned(requirement, employee)
            candidates = await repository.list_completed_history(
                exclude_requirement_id=requirement.id
            )

            grouped: dict[str, dict[str, object]] = {}
            for order, historical_requirement in candidates:
                supplier_name = order.supplier_name or historical_requirement.supplier_name
                if not supplier_name:
                    continue
                score, matched_fields = self._history_score(
                    requirement,
                    historical_requirement,
                )
                if score == 0:
                    continue
                key = (
                    f"id:{order.supplier_id}"
                    if order.supplier_id is not None
                    else f"name:{supplier_name.casefold()}"
                )
                current = grouped.get(key)
                if current is None:
                    grouped[key] = {
                        "score": score,
                        "matched_fields": matched_fields,
                        "supplier_id": order.supplier_id,
                        "supplier_name": supplier_name,
                        "count": 1,
                        "order": order,
                        "requirement": historical_requirement,
                    }
                    continue
                current["count"] = int(current["count"]) + 1
                if score > current["score"]:
                    current["score"] = score
                    current["matched_fields"] = matched_fields

            ranked = sorted(
                grouped.values(),
                key=lambda item: (
                    item["score"],
                    item["count"],
                    item["order"].received_at or item["order"].created_at or datetime.min,
                ),
                reverse=True,
            )[: query.limit]
            recommendations = [
                self._to_historical_recommendation(rank, item)
                for rank, item in enumerate(ranked, start=1)
            ]
            return HistoricalSupplierRecommendationResult(
                query_summary=self._query_summary(requirement),
                result_code="OK" if recommendations else "NO_HISTORY_MATCH",
                recommendations=recommendations,
            )

    async def submit(
        self,
        requirement_id: int,
        command: SubmitRequirement,
        context: AuditContext,
    ) -> RequirementSubmissionResult:
        """只有员工明确确认后才进入审批流程。"""
        payload = command.model_dump(mode="json")
        request_hash = _request_hash(payload)
        operation = f"submit_requirement:{requirement_id}"
        now = _utc_naive(self._clock())

        async with transaction_scope(self._session_factory) as session:
            repository = RequirementRepository(session)
            replay = await self._idempotent_submission_replay(
                repository,
                actor_code=context.actor.user_code,
                operation=operation,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if replay is not None:
                return replay

            employee = await self._require_employee(repository, context.actor)
            requirement = await repository.get_requirement_for_update(requirement_id)
            self._require_owned(requirement, employee)
            self._require_draft_version(requirement, command.version)
            missing_fields = self._missing_fields(requirement)
            if missing_fields:
                raise DomainError(
                    ErrorCode.REQUIREMENT_INCOMPLETE,
                    "采购申请缺少提交审批所需的必填信息",
                    [
                        {"field": field, "reason": "required_for_submission"}
                        for field in missing_fields
                    ],
                )
            if command.recommendation_id is not None:
                recommendation = await repository.get_recommendation(command.recommendation_id)
                if recommendation is None or recommendation.requirement_id != requirement.id:
                    raise DomainError(
                        ErrorCode.RESOURCE_NOT_FOUND,
                        "当前采购申请中不存在所选推荐记录",
                        [{"field": "recommendation_id", "reason": "not_found"}],
                    )
                recommendation.selected = True

            previous_status = requirement.status
            requirement.status = "PENDING_APPROVAL"
            requirement.submitted_at = now
            requirement.applicant_employee_no = employee.employee_no
            requirement.applicant_name = employee.name
            requirement.applicant_phone = employee.phone
            requirement.total_amount = self._calculate_total(
                requirement.quantity, requirement.unit_price
            )
            requirement.version += 1
            requirement.updated_at = now
            repository.add_status_history(
                self._status_history(
                    requirement=requirement,
                    employee=employee,
                    from_status=previous_status,
                    to_status="PENDING_APPROVAL",
                    context=context,
                    remark="员工确认采购申请并提交审批",
                    changed_at=now,
                )
            )
            await repository.flush()

            result = RequirementSubmissionResult(
                requirement_id=requirement.id,
                requirement_no=requirement.requirement_no,
                status="PENDING_APPROVAL",
                version=requirement.version,
                submitted_at=_utc_aware(requirement.submitted_at),
            )
            repository.add_idempotency_record(
                self._idempotency_record(
                    context=context,
                    operation=operation,
                    request_hash=request_hash,
                    resource_id=requirement.id,
                    response=result,
                    created_at=now,
                )
            )
            await repository.flush()
            return result

    async def cancel_draft(
        self,
        requirement_id: int,
        command: CancelRequirementDraft,
        context: AuditContext,
    ) -> RequirementDetail:
        """取消员工本人的草稿，并保留只追加的状态变更记录。"""
        payload = command.model_dump(mode="json")
        request_hash = _request_hash(payload)
        operation = f"cancel_requirement:{requirement_id}"
        now = _utc_naive(self._clock())

        async with transaction_scope(self._session_factory) as session:
            repository = RequirementRepository(session)
            replay = await self._idempotent_replay(
                repository,
                actor_code=context.actor.user_code,
                operation=operation,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if replay is not None:
                return replay

            employee = await self._require_employee(repository, context.actor)
            requirement = await repository.get_requirement_for_update(requirement_id)
            self._require_owned(requirement, employee)
            self._require_draft_version(requirement, command.version)
            previous_status = requirement.status
            requirement.status = "CANCELLED"
            requirement.version += 1
            requirement.updated_at = now
            repository.add_status_history(
                self._status_history(
                    requirement=requirement,
                    employee=employee,
                    from_status=previous_status,
                    to_status="CANCELLED",
                    context=context,
                    remark=command.reason,
                    changed_at=now,
                )
            )
            await repository.flush()
            detail = self._to_detail(requirement, employee)
            repository.add_idempotency_record(
                self._idempotency_record(
                    context=context,
                    operation=operation,
                    request_hash=request_hash,
                    resource_id=requirement.id,
                    response=detail,
                    created_at=now,
                )
            )
            await repository.flush()
            return detail

    async def revise_rejected(
        self,
        requirement_id: int,
        command: ReviseRejectedRequirement,
        context: AuditContext,
    ) -> RequirementDetail:
        """保留被驳回申请，复制业务快照形成下一版本草稿。"""
        payload = command.model_dump(mode="json")
        request_hash = _request_hash(payload)
        operation = f"revise_rejected_requirement:{requirement_id}"
        now_aware = self._clock()
        now = _utc_naive(now_aware)
        async with transaction_scope(self._session_factory) as session:
            repository = RequirementRepository(session)
            replay = await self._idempotent_replay(
                repository,
                actor_code=context.actor.user_code,
                operation=operation,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if replay is not None:
                return replay
            employee = await self._require_employee(repository, context.actor)
            previous = await repository.get_requirement_for_update(requirement_id)
            self._require_owned(previous, employee)
            if previous.status != "REJECTED":
                raise DomainError(ErrorCode.STATE_CONFLICT, "只有被驳回的申请可以创建修改版本")
            if previous.version != command.version:
                raise DomainError(ErrorCode.VERSION_CONFLICT, "申请已更新，请刷新后重试")
            revised = PurchaseRequirement(
                requirement_no=self._number_factory(now_aware),
                employee_id=employee.id,
                applicant_employee_no=employee.employee_no,
                applicant_name=employee.name,
                applicant_phone=employee.phone,
                requested_at=now,
                submitted_at=None,
                revision_no=previous.revision_no + 1,
                previous_requirement_id=previous.id,
                status="DRAFT",
                quantity_raw=previous.quantity_raw,
                unit_price_raw=previous.unit_price_raw,
                source_reference=None,
                updated_at=now,
                version=1,
                total_amount=previous.total_amount,
                session_id=None,
                building_id=previous.building_id,
                category_id=previous.category_id,
                category_name=previous.category_name,
                application_reason=previous.application_reason,
                application_location=previous.application_location,
                device_type=previous.device_type,
                product_id=previous.product_id,
                product_name=previous.product_name,
                product_full_name=previous.product_full_name,
                brand=previous.brand,
                model=previous.model,
                specification=previous.specification,
                quantity=previous.quantity,
                unit=previous.unit,
                supplier_id=previous.supplier_id,
                supplier_name=previous.supplier_name,
                unit_price=previous.unit_price,
                currency=previous.currency,
            )
            repository.add_requirement(revised)
            await repository.flush()
            repository.add_status_history(
                self._status_history(
                    requirement=revised,
                    employee=employee,
                    from_status="REJECTED",
                    to_status="DRAFT",
                    context=context,
                    remark=f"基于被驳回申请 {previous.requirement_no} 创建修改版本",
                    changed_at=now,
                )
            )
            detail = self._to_detail(revised, employee)
            repository.add_idempotency_record(
                self._idempotency_record(
                    context=context,
                    operation=operation,
                    request_hash=request_hash,
                    resource_id=revised.id,
                    response=detail,
                    created_at=now,
                )
            )
            await repository.flush()
            return detail

    @staticmethod
    def _require_draft_version(
        requirement: PurchaseRequirement,
        expected_version: int,
    ) -> None:
        if requirement.status != "DRAFT":
            raise DomainError(
                ErrorCode.STATE_CONFLICT,
                "只有草稿状态的采购申请允许执行此操作",
                [{"status": requirement.status}],
            )
        if requirement.version != expected_version:
            raise DomainError(
                ErrorCode.VERSION_CONFLICT,
                "采购申请已被其他请求更新，请刷新后重试",
                [{"expected_version": expected_version, "actual_version": requirement.version}],
            )

    @staticmethod
    def _status_history(
        *,
        requirement: PurchaseRequirement,
        employee: Employee,
        from_status: str,
        to_status: str,
        context: AuditContext,
        remark: str,
        changed_at: datetime,
    ) -> PurchaseStatusHistory:
        return PurchaseStatusHistory(
            requirement_id=requirement.id,
            order_id=None,
            from_status=from_status,
            to_status=to_status,
            operator_id=employee.id,
            operator_employee_no=employee.employee_no,
            operator_name=employee.name,
            operator_phone=employee.phone,
            remark=remark,
            changed_at=changed_at,
            request_id=context.request_id,
            created_at=changed_at,
        )

    @staticmethod
    def _to_summary(requirement: PurchaseRequirement) -> RequirementSummary:
        return RequirementSummary(
            requirement_id=requirement.id,
            requirement_no=requirement.requirement_no,
            product_name=requirement.product_name,
            status=requirement.status,
            total_amount=requirement.total_amount,
            currency=requirement.currency,
            updated_at=_utc_aware(requirement.updated_at),
            version=requirement.version,
        )

    @staticmethod
    def _normalized(value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        return " ".join(value.casefold().split())

    @classmethod
    def _history_score(
        cls,
        requirement: PurchaseRequirement,
        historical: PurchaseRequirement,
    ) -> tuple[Decimal, list[str]]:
        score = Decimal("0")
        matched: list[str] = []
        comparisons = (
            (
                "product_id",
                requirement.product_id,
                historical.product_id,
                Decimal("0.4500"),
            ),
            ("model", requirement.model, historical.model, Decimal("0.2000")),
            ("brand", requirement.brand, historical.brand, Decimal("0.1000")),
            (
                "product_name",
                requirement.product_name,
                historical.product_name,
                Decimal("0.1500"),
            ),
            (
                "product_full_name",
                requirement.product_full_name,
                historical.product_full_name,
                Decimal("0.0500"),
            ),
            (
                "device_type",
                requirement.device_type,
                historical.device_type,
                Decimal("0.0500"),
            ),
        )
        for field, current_value, historical_value, weight in comparisons:
            if field == "product_id":
                is_match = current_value is not None and current_value == historical_value
            else:
                is_match = cls._normalized(current_value) is not None and cls._normalized(
                    current_value
                ) == cls._normalized(historical_value)
            if is_match:
                score += weight
                matched.append(field)
        return score.quantize(Decimal("0.0001")), matched

    @classmethod
    def _query_summary(cls, requirement: PurchaseRequirement) -> str:
        values = [
            requirement.product_name,
            requirement.brand,
            requirement.model,
        ]
        return " / ".join(value for value in values if cls._normalized(value)) or "未命名商品"

    @classmethod
    def _to_historical_recommendation(
        cls,
        rank: int,
        item: dict[str, object],
    ) -> HistoricalSupplierRecommendation:
        order = item["order"]
        requirement = item["requirement"]
        if not isinstance(order, PurchaseOrder) or not isinstance(requirement, PurchaseRequirement):
            raise RuntimeError("历史推荐候选记录无效")
        unit_price = order.unit_price
        if unit_price is None and order.amount is not None and order.quantity:
            unit_price = (order.amount / order.quantity).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        count = int(item["count"])
        matched_fields = list(item["matched_fields"])
        reason_fields = "、".join(matched_fields)
        return HistoricalSupplierRecommendation(
            rank=rank,
            match_score=Decimal(item["score"]),
            matched_fields=matched_fields,
            supplier_id=item["supplier_id"],
            supplier_name=str(item["supplier_name"]),
            historical_order_count=count,
            latest_purchase=HistoricalPurchaseSummary(
                requirement_id=requirement.id,
                requirement_no=requirement.requirement_no,
                order_id=order.id,
                order_no=order.order_no,
                product_name=requirement.product_full_name or requirement.product_name,
                brand=requirement.brand,
                model=requirement.model,
                quantity=order.quantity,
                unit=requirement.unit,
                unit_price=unit_price,
                currency=requirement.currency,
                purchased_at=_utc_aware(order.created_at),
                received_at=_utc_aware(order.received_at),
                status=order.status or "COMPLETED",
            ),
            reason=f"历史记录匹配字段：{reason_fields}；该供应商有 {count} 条相似已完成采购记录。",
            warnings=["历史价格仅供参考，不代表当前报价。"],
        )

    @staticmethod
    def _draft_values(command: CreateRequirementDraft) -> dict[str, object]:
        values = {field: _clean_text(getattr(command, field)) for field in _EDITABLE_FIELDS}
        return values

    async def _resolve_associations(
        self,
        repository: RequirementRepository,
        requirement: PurchaseRequirement,
        supplied_fields: set[str],
    ) -> None:
        if requirement.building_id is not None:
            building = await repository.get_building(requirement.building_id)
            if building is None:
                self._association_not_found("building_id")

        if requirement.category_id is not None:
            category = await repository.get_category(requirement.category_id)
            if category is None:
                self._association_not_found("category_id")
            if "category_name" not in supplied_fields or not requirement.category_name:
                requirement.category_name = category.name

        if requirement.product_id is not None:
            product = await repository.get_product(requirement.product_id)
            if product is None:
                self._association_not_found("product_id")
            snapshot_fields = {
                "product_name": product.product_name,
                "brand": product.brand,
                "model": product.model,
                "specification": product.specification,
                "unit": product.unit,
            }
            for field, value in snapshot_fields.items():
                if field not in supplied_fields or not getattr(requirement, field):
                    setattr(requirement, field, value)
            if requirement.category_id is None and product.category_id is not None:
                requirement.category_id = product.category_id
                category = await repository.get_category(product.category_id)
                if category is not None and not requirement.category_name:
                    requirement.category_name = category.name

        if requirement.supplier_id is not None:
            supplier = await repository.get_supplier(requirement.supplier_id)
            if supplier is None:
                self._association_not_found("supplier_id")
            if "supplier_name" not in supplied_fields or not requirement.supplier_name:
                requirement.supplier_name = supplier.supplier_name

    @staticmethod
    def _association_not_found(field: str) -> None:
        raise DomainError(
            ErrorCode.RESOURCE_NOT_FOUND,
            "没有找到关联的主数据",
            [{"field": field, "reason": "not_found"}],
        )

    @staticmethod
    async def _require_employee(
        repository: RequirementRepository,
        actor: CurrentUser,
    ) -> Employee:
        employee = await repository.get_employee_by_no(actor.user_code)
        if employee is None:
            raise DomainError(
                ErrorCode.EMPLOYEE_NOT_MAPPED,
                "当前登录用户未关联有效员工记录",
                [{"field": "current_user", "reason": "employee_not_mapped"}],
            )
        return employee

    @staticmethod
    def _require_owned(
        requirement: PurchaseRequirement | None,
        employee: Employee,
    ) -> None:
        if requirement is None:
            raise DomainError(ErrorCode.RESOURCE_NOT_FOUND, "没有找到该采购申请")
        if requirement.employee_id != employee.id:
            raise DomainError(ErrorCode.FORBIDDEN, "无权访问该采购申请")

    @staticmethod
    def _calculate_total(
        quantity: Decimal | None,
        unit_price: Decimal | None,
    ) -> Decimal | None:
        if quantity is None or unit_price is None:
            return None
        return (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _missing_fields(requirement: PurchaseRequirement) -> list[str]:
        return [
            field
            for field in _REQUIRED_FOR_SUBMISSION
            if getattr(requirement, field) is None
            or (isinstance(getattr(requirement, field), str) and not getattr(requirement, field))
        ]

    def _to_detail(
        self,
        requirement: PurchaseRequirement,
        employee: Employee,
    ) -> RequirementDetail:
        warnings: list[RequirementNotice] = []
        if requirement.product_id is None and requirement.product_name:
            warnings.append(
                RequirementNotice(
                    code="PRODUCT_NOT_IN_MASTER_DATA",
                    message="该商品尚未匹配产品主数据，提交后需要人工核实。",
                )
            )
        if requirement.supplier_id is None and requirement.supplier_name:
            warnings.append(
                RequirementNotice(
                    code="SUPPLIER_NOT_IN_MASTER_DATA",
                    message="该供应商尚未进入供应商主数据，提交后由采购人员核实。",
                )
            )
        return RequirementDetail(
            requirement_id=requirement.id,
            requirement_no=requirement.requirement_no,
            status=requirement.status,
            version=requirement.version,
            applicant=ApplicantSnapshot(
                employee_no=requirement.applicant_employee_no or employee.employee_no,
                name=requirement.applicant_name or employee.name,
                phone=requirement.applicant_phone or employee.phone,
            ),
            session_id=requirement.session_id,
            building_id=requirement.building_id,
            category_id=requirement.category_id,
            category_name=requirement.category_name,
            application_reason=requirement.application_reason,
            application_location=requirement.application_location,
            device_type=requirement.device_type,
            product_id=requirement.product_id,
            product_name=requirement.product_name,
            product_full_name=requirement.product_full_name,
            brand=requirement.brand,
            model=requirement.model,
            specification=requirement.specification,
            quantity=requirement.quantity,
            unit=requirement.unit,
            supplier_id=requirement.supplier_id,
            supplier_name=requirement.supplier_name,
            unit_price=requirement.unit_price,
            total_amount=requirement.total_amount,
            currency=requirement.currency,
            new_product=requirement.product_id is None and bool(requirement.product_name),
            new_supplier=requirement.supplier_id is None and bool(requirement.supplier_name),
            missing_fields=self._missing_fields(requirement),
            conflicts=[],
            warnings=warnings,
            requested_at=_utc_aware(requirement.requested_at),
            submitted_at=_utc_aware(requirement.submitted_at),
            updated_at=_utc_aware(requirement.updated_at),
        )

    @staticmethod
    async def _idempotent_replay(
        repository: RequirementRepository,
        *,
        actor_code: str,
        operation: str,
        idempotency_key: str,
        request_hash: str,
    ) -> RequirementDetail | None:
        record = await repository.get_idempotency_record(
            actor_code=actor_code,
            operation=operation,
            idempotency_key=idempotency_key,
        )
        if record is None:
            return None
        if record.request_hash != request_hash:
            raise DomainError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "该幂等键已被其他请求使用",
            )
        return RequirementDetail.model_validate(record.response_payload)

    @staticmethod
    async def _idempotent_submission_replay(
        repository: RequirementRepository,
        *,
        actor_code: str,
        operation: str,
        idempotency_key: str,
        request_hash: str,
    ) -> RequirementSubmissionResult | None:
        record = await repository.get_idempotency_record(
            actor_code=actor_code,
            operation=operation,
            idempotency_key=idempotency_key,
        )
        if record is None:
            return None
        if record.request_hash != request_hash:
            raise DomainError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "该幂等键已被其他请求使用",
            )
        return RequirementSubmissionResult.model_validate(record.response_payload)

    @staticmethod
    def _idempotency_record(
        *,
        context: AuditContext,
        operation: str,
        request_hash: str,
        resource_id: int,
        response: BaseModel,
        created_at: datetime,
    ) -> IdempotencyRecord:
        return IdempotencyRecord(
            actor_code=context.actor.user_code,
            operation=operation,
            idempotency_key=context.idempotency_key,
            request_hash=request_hash,
            resource_type="purchase_requirement",
            resource_id=resource_id,
            response_payload=response.model_dump(mode="json"),
            created_at=created_at,
        )
