"""楼长审批与采购执行的权限、状态机、幂等和事务规则。"""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel

from app.infrastructure.database import AsyncSessionFactory, session_scope, transaction_scope
from app.modules.auth.models import Building
from app.modules.requirement.models import (
    Employee,
    IdempotencyRecord,
    PurchaseApproval,
    PurchaseOrder,
    PurchaseRequirement,
    PurchaseStatusHistory,
)
from app.modules.workflow.repository import WorkflowRepository
from app.modules.workflow.schemas import (
    AdvanceProcurement,
    ApprovalDecision,
    ApprovalDecisionResult,
    ApprovalTaskView,
    BuildingOption,
    CompleteProcurement,
    ProcurementTaskView,
    RollbackProcurement,
    StartProcurement,
    WorkflowApplicant,
)
from app.shared.errors import DomainError, ErrorCode
from app.shared.identity import AuditContext, CurrentUser

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _utc_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _request_hash(payload: dict[str, object]) -> str:
    value = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class WorkflowService:
    """完成楼长审批并把通过的申请交给采购人员闭环处理。"""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    async def list_buildings(self) -> list[BuildingOption]:
        async with session_scope(self._session_factory) as session:
            buildings = await WorkflowRepository(session).list_buildings()
            return [
                BuildingOption(
                    building_id=building.id,
                    building_code=building.building_code,
                    building_name=building.building_name,
                )
                for building in buildings
            ]

    async def list_approval_tasks(
        self, actor: CurrentUser, *, view: str, page: int, page_size: int
    ) -> tuple[list[ApprovalTaskView], int]:
        self._require_role(actor, "BUILDING_MANAGER", "只有楼长可以查看待审批申请")
        if actor.employee_id is None:
            return [], 0
        async with session_scope(self._session_factory) as session:
            rows, total = await WorkflowRepository(session).list_approval_tasks(
                approver_id=actor.employee_id,
                view=view,
                page=page,
                page_size=page_size,
            )
            return [
                self._approval_view(requirement, building, approval)
                for requirement, building, approval in rows
            ], total

    async def get_approval_task(self, requirement_id: int, actor: CurrentUser) -> ApprovalTaskView:
        self._require_role(actor, "BUILDING_MANAGER", "只有楼长可以查看审批详情")
        async with session_scope(self._session_factory) as session:
            row = await WorkflowRepository(session).get_requirement_with_building(requirement_id)
            if row is None:
                raise DomainError(ErrorCode.RESOURCE_NOT_FOUND, "没有找到该待审批申请")
            requirement, building = row
            approval = None
            if requirement.status != "PENDING_APPROVAL":
                if actor.employee_id is None:
                    raise DomainError(ErrorCode.FORBIDDEN, "当前楼长账号未关联员工信息")
                approval = await WorkflowRepository(session).get_approval_for_actor(
                    requirement_id, actor.employee_id
                )
                if approval is None:
                    raise DomainError(ErrorCode.FORBIDDEN, "只能查看本人处理过的审批记录")
            return self._approval_view(requirement, building, approval)

    async def decide(
        self,
        requirement_id: int,
        command: ApprovalDecision,
        context: AuditContext,
    ) -> ApprovalDecisionResult:
        self._require_role(context.actor, "BUILDING_MANAGER", "只有楼长可以执行审批")
        if command.action == "REJECTED" and not (command.comment or "").strip():
            raise DomainError(ErrorCode.VALIDATION_ERROR, "驳回采购申请时必须填写审批意见")
        operation = f"approval_decision:{requirement_id}"
        request_hash = _request_hash(command.model_dump(mode="json"))
        now = _utc_naive(self._clock())

        async with transaction_scope(self._session_factory) as session:
            repository = WorkflowRepository(session)
            replay = await self._replay(
                repository,
                actor_code=context.actor.user_code,
                operation=operation,
                key=context.idempotency_key,
                request_hash=request_hash,
                model=ApprovalDecisionResult,
            )
            if replay is not None:
                return replay
            employee = await self._require_employee(repository, context.actor)
            requirement = await repository.get_requirement_for_update(requirement_id)
            if requirement is None:
                raise DomainError(ErrorCode.RESOURCE_NOT_FOUND, "没有找到该采购申请")
            if requirement.status != "PENDING_APPROVAL":
                raise DomainError(ErrorCode.STATE_CONFLICT, "该申请已被其他楼长处理")
            if requirement.version != command.version:
                raise DomainError(ErrorCode.VERSION_CONFLICT, "申请内容已更新，请刷新后重新审批")

            previous_status = requirement.status
            requirement.status = command.action
            requirement.version += 1
            requirement.updated_at = now
            repository.add(
                PurchaseApproval(
                    requirement_id=requirement.id,
                    revision_no=requirement.revision_no,
                    approver_id=employee.id,
                    approver_employee_no=employee.employee_no,
                    approver_name=employee.name,
                    approver_phone=employee.phone,
                    action=command.action,
                    comment=command.comment,
                    submitted_at=requirement.submitted_at or now,
                    acted_at=now,
                    idempotency_key=context.idempotency_key,
                    created_at=now,
                )
            )
            repository.add(
                self._history(
                    requirement=requirement,
                    order=None,
                    employee=employee,
                    from_status=previous_status,
                    to_status=command.action,
                    remark=command.comment
                    or ("审批通过" if command.action == "APPROVED" else "审批驳回"),
                    context=context,
                    now=now,
                )
            )
            result = ApprovalDecisionResult(
                requirement_id=requirement.id,
                requirement_no=requirement.requirement_no,
                status=command.action,
                version=requirement.version,
                acted_at=_utc_aware(now),
            )
            repository.add(
                self._idempotency(
                    context=context,
                    operation=operation,
                    request_hash=request_hash,
                    resource_type="purchase_requirement",
                    resource_id=requirement.id,
                    response=result,
                    now=now,
                )
            )
            await repository.flush()
            return result

    async def list_procurement_tasks(
        self, actor: CurrentUser, *, page: int, page_size: int
    ) -> tuple[list[ProcurementTaskView], int]:
        self._require_role(actor, "PURCHASER", "只有采购员可以查看采购任务")
        async with session_scope(self._session_factory) as session:
            rows, total = await WorkflowRepository(session).list_procurement_tasks(
                page=page, page_size=page_size
            )
            return [self._procurement_view(*row) for row in rows], total

    async def start_procurement(
        self,
        requirement_id: int,
        command: StartProcurement,
        context: AuditContext,
    ) -> ProcurementTaskView:
        self._require_role(context.actor, "PURCHASER", "只有采购员可以开始采购")
        operation = f"start_procurement:{requirement_id}"
        return await self._procurement_write(
            operation=operation,
            payload=command,
            context=context,
            handler=lambda repository, employee, now: self._start(
                repository, employee, requirement_id, command, context, now
            ),
        )

    async def advance_procurement(
        self,
        order_id: int,
        command: AdvanceProcurement,
        context: AuditContext,
    ) -> ProcurementTaskView:
        self._require_role(context.actor, "PURCHASER", "只有采购员可以更新采购进度")
        operation = f"advance_procurement:{order_id}"
        return await self._procurement_write(
            operation=operation,
            payload=command,
            context=context,
            handler=lambda repository, employee, now: self._advance(
                repository, employee, order_id, command, context, now
            ),
        )

    async def complete_procurement(
        self,
        order_id: int,
        command: CompleteProcurement,
        context: AuditContext,
    ) -> ProcurementTaskView:
        self._require_role(context.actor, "PURCHASER", "只有采购员可以确认验收入库")
        operation = f"complete_procurement:{order_id}"
        return await self._procurement_write(
            operation=operation,
            payload=command,
            context=context,
            handler=lambda repository, employee, now: self._complete(
                repository, employee, order_id, command, context, now
            ),
        )

    async def rollback_procurement(
        self,
        order_id: int,
        command: RollbackProcurement,
        context: AuditContext,
    ) -> ProcurementTaskView:
        self._require_role(context.actor, "PURCHASER", "只有采购员可以撤回采购节点")
        operation = f"rollback_procurement:{order_id}"
        return await self._procurement_write(
            operation=operation,
            payload=command,
            context=context,
            handler=lambda repository, employee, now: self._rollback(
                repository, employee, order_id, command, context, now
            ),
        )

    async def _procurement_write(self, *, operation, payload, context, handler):
        request_hash = _request_hash(payload.model_dump(mode="json"))
        now = _utc_naive(self._clock())
        async with transaction_scope(self._session_factory) as session:
            repository = WorkflowRepository(session)
            replay = await self._replay(
                repository,
                actor_code=context.actor.user_code,
                operation=operation,
                key=context.idempotency_key,
                request_hash=request_hash,
                model=ProcurementTaskView,
            )
            if replay is not None:
                return replay
            employee = await self._require_employee(repository, context.actor)
            result = await handler(repository, employee, now)
            repository.add(
                self._idempotency(
                    context=context,
                    operation=operation,
                    request_hash=request_hash,
                    resource_type="purchase_order",
                    resource_id=result.order_id,
                    response=result,
                    now=now,
                )
            )
            await repository.flush()
            return result

    async def _start(self, repository, employee, requirement_id, command, context, now):
        requirement = await repository.get_requirement_for_update(requirement_id)
        if requirement is None:
            raise DomainError(ErrorCode.RESOURCE_NOT_FOUND, "没有找到审批通过的采购申请")
        if requirement.status != "APPROVED":
            raise DomainError(ErrorCode.STATE_CONFLICT, "只有审批通过的申请可以开始采购")
        if requirement.version != command.version:
            raise DomainError(ErrorCode.VERSION_CONFLICT, "申请已更新，请刷新采购任务")
        if requirement.quantity is None:
            raise DomainError(ErrorCode.STATE_CONFLICT, "采购申请缺少数量，不能生成采购单")
        order = await repository.get_order_by_requirement(requirement.id)
        if order is None:
            order = PurchaseOrder(
                order_no=f"PO-{now:%Y%m%d}-{uuid4().hex[:12].upper()}",
                requirement_id=requirement.id,
                product_id=requirement.product_id,
                supplier_id=requirement.supplier_id,
                quantity=requirement.quantity,
                amount=requirement.total_amount,
                status="PURCHASING",
                created_at=now,
                supplier_name=requirement.supplier_name,
                unit_price=requirement.unit_price,
                purchaser_id=employee.id,
                purchaser_employee_no=employee.employee_no,
                purchaser_name=employee.name,
                purchaser_phone=employee.phone,
                purchasing_started_at=now,
                quoted_at=None,
                contracted_at=None,
                received_at=None,
                completed_at=None,
                updated_at=now,
                version=1,
            )
            repository.add(order)
            await repository.flush()
        elif order.purchaser_id is not None:
            raise DomainError(ErrorCode.STATE_CONFLICT, "该采购任务已被其他采购员领取")
        else:
            order.status = "PURCHASING"
            order.purchaser_id = employee.id
            order.purchaser_employee_no = employee.employee_no
            order.purchaser_name = employee.name
            order.purchaser_phone = employee.phone
            order.purchasing_started_at = now
            order.updated_at = now
            order.version += 1
        requirement.status = "PURCHASING"
        requirement.version += 1
        requirement.updated_at = now
        repository.add(
            self._history(
                requirement=requirement,
                order=order,
                employee=employee,
                from_status="APPROVED",
                to_status="PURCHASING",
                remark="采购员领取任务并开始采购",
                context=context,
                now=now,
            )
        )
        building = (
            await repository.get_building(requirement.building_id)
            if requirement.building_id
            else None
        )
        approval = await repository.get_latest_approval(requirement.id)
        return self._procurement_view(requirement, building, order, approval)

    async def _advance(self, repository, employee, order_id, command, context, now):
        order = await repository.get_order_for_update(order_id)
        if order is None:
            raise DomainError(ErrorCode.RESOURCE_NOT_FOUND, "没有找到该采购单")
        self._require_assigned_purchaser(order, employee)
        if order.version != command.version:
            raise DomainError(ErrorCode.VERSION_CONFLICT, "采购单已更新，请刷新后重试")
        expected = {"QUOTED": "PURCHASING", "CONTRACTED": "QUOTED"}[command.target_status]
        if order.status != expected:
            raise DomainError(
                ErrorCode.STATE_CONFLICT,
                f"当前采购状态不能变更为 {command.target_status}",
            )
        requirement = await repository.get_requirement_for_update(order.requirement_id)
        if requirement is None:
            raise DomainError(ErrorCode.RESOURCE_NOT_FOUND, "采购单关联的申请不存在")
        previous_status = order.status
        order.status = command.target_status
        order.quoted_at = now if command.target_status == "QUOTED" else order.quoted_at
        order.contracted_at = now if command.target_status == "CONTRACTED" else order.contracted_at
        order.updated_at = now
        order.version += 1
        requirement.status = command.target_status
        requirement.updated_at = now
        requirement.version += 1
        repository.add(
            self._history(
                requirement=requirement,
                order=order,
                employee=employee,
                from_status=previous_status,
                to_status=command.target_status,
                remark=command.remark
                or ("已完成询价核价" if command.target_status == "QUOTED" else "已完成合同签订"),
                context=context,
                now=now,
            )
        )
        building = (
            await repository.get_building(requirement.building_id)
            if requirement.building_id
            else None
        )
        approval = await repository.get_latest_approval(requirement.id)
        return self._procurement_view(requirement, building, order, approval)

    async def _complete(self, repository, employee, order_id, command, context, now):
        order = await repository.get_order_for_update(order_id)
        if order is None:
            raise DomainError(ErrorCode.RESOURCE_NOT_FOUND, "没有找到该采购单")
        self._require_assigned_purchaser(order, employee)
        if order.version != command.version:
            raise DomainError(ErrorCode.VERSION_CONFLICT, "采购单已更新，请刷新后重试")
        if order.status != "CONTRACTED":
            raise DomainError(ErrorCode.STATE_CONFLICT, "当前采购状态不能执行验收入库")
        requirement = await repository.get_requirement_for_update(order.requirement_id)
        if requirement is None:
            raise DomainError(ErrorCode.RESOURCE_NOT_FOUND, "采购单关联的申请不存在")
        previous_status = order.status or requirement.status
        order.status = "COMPLETED"
        order.received_at = now
        order.completed_at = now
        order.updated_at = now
        order.version += 1
        requirement.status = "COMPLETED"
        requirement.updated_at = now
        requirement.version += 1
        repository.add(
            self._history(
                requirement=requirement,
                order=order,
                employee=employee,
                from_status=previous_status,
                to_status="COMPLETED",
                remark=command.remark or "设备已验收入库，采购完成",
                context=context,
                now=now,
            )
        )
        building = (
            await repository.get_building(requirement.building_id)
            if requirement.building_id
            else None
        )
        approval = await repository.get_latest_approval(requirement.id)
        return self._procurement_view(requirement, building, order, approval)

    async def _rollback(self, repository, employee, order_id, command, context, now):
        order = await repository.get_order_for_update(order_id)
        if order is None:
            raise DomainError(ErrorCode.RESOURCE_NOT_FOUND, "没有找到该采购单")
        self._require_assigned_purchaser(order, employee)
        if order.version != command.version:
            raise DomainError(ErrorCode.VERSION_CONFLICT, "采购单已更新，请刷新后重试")
        targets = {
            "PURCHASING": "APPROVED",
            "QUOTED": "PURCHASING",
            "CONTRACTED": "QUOTED",
            "COMPLETED": "CONTRACTED",
        }
        previous_status = order.status or ""
        target_status = targets.get(previous_status)
        if target_status is None:
            raise DomainError(ErrorCode.STATE_CONFLICT, "当前采购状态没有可撤回的上一步")
        requirement = await repository.get_requirement_for_update(order.requirement_id)
        if requirement is None:
            raise DomainError(ErrorCode.RESOURCE_NOT_FOUND, "采购单关联的申请不存在")

        order.status = "CREATED" if target_status == "APPROVED" else target_status
        if previous_status == "PURCHASING":
            order.purchaser_id = None
            order.purchaser_employee_no = None
            order.purchaser_name = None
            order.purchaser_phone = None
            order.purchasing_started_at = None
        elif previous_status == "QUOTED":
            order.quoted_at = None
        elif previous_status == "CONTRACTED":
            order.contracted_at = None
        else:
            order.received_at = None
            order.completed_at = None
        order.updated_at = now
        order.version += 1
        requirement.status = target_status
        requirement.updated_at = now
        requirement.version += 1
        repository.add(
            self._history(
                requirement=requirement,
                order=order,
                employee=employee,
                from_status=previous_status,
                to_status=target_status,
                remark="采购员确认撤回上一采购节点",
                context=context,
                now=now,
            )
        )
        building = (
            await repository.get_building(requirement.building_id)
            if requirement.building_id
            else None
        )
        approval = await repository.get_latest_approval(requirement.id)
        return self._procurement_view(requirement, building, order, approval)

    @staticmethod
    def _require_role(actor: CurrentUser, role: str, message: str) -> None:
        if role not in actor.roles:
            raise DomainError(ErrorCode.FORBIDDEN, message)

    @staticmethod
    async def _require_employee(repository, actor) -> Employee:
        employee = await repository.get_employee_by_no(actor.user_code)
        if employee is None:
            raise DomainError(ErrorCode.EMPLOYEE_NOT_MAPPED, "当前账号未关联有效员工")
        return employee

    @staticmethod
    def _require_assigned_purchaser(order: PurchaseOrder, employee: Employee) -> None:
        if order.purchaser_id != employee.id:
            raise DomainError(ErrorCode.FORBIDDEN, "该采购任务已由其他采购员负责")

    @staticmethod
    def _approval_view(
        requirement: PurchaseRequirement,
        building: Building | None,
        approval: PurchaseApproval | None = None,
    ) -> ApprovalTaskView:
        return ApprovalTaskView(
            requirement_id=requirement.id,
            requirement_no=requirement.requirement_no,
            status=requirement.status,
            version=requirement.version,
            revision_no=requirement.revision_no,
            building_id=building.id if building else None,
            building_name=building.building_name if building else None,
            applicant=WorkflowApplicant(
                employee_id=requirement.employee_id,
                employee_no=requirement.applicant_employee_no,
                name=requirement.applicant_name or "未登记员工",
                phone=requirement.applicant_phone,
            ),
            category_name=requirement.category_name,
            application_reason=requirement.application_reason,
            application_location=requirement.application_location,
            device_type=requirement.device_type,
            product_name=requirement.product_name,
            product_full_name=requirement.product_full_name,
            brand=requirement.brand,
            model=requirement.model,
            specification=requirement.specification,
            quantity=requirement.quantity,
            unit=requirement.unit,
            supplier_name=requirement.supplier_name,
            unit_price=requirement.unit_price,
            total_amount=requirement.total_amount,
            currency=requirement.currency,
            submitted_at=_utc_aware(requirement.submitted_at),
            updated_at=_utc_aware(requirement.updated_at),
            approval_action=approval.action if approval else None,
            approval_comment=approval.comment if approval else None,
            approver_employee_no=approval.approver_employee_no if approval else None,
            approver_name=approval.approver_name if approval else None,
            approver_phone=approval.approver_phone if approval else None,
            acted_at=_utc_aware(approval.acted_at) if approval else None,
        )

    @staticmethod
    def _procurement_view(requirement, building, order, approval=None) -> ProcurementTaskView:
        return ProcurementTaskView(
            requirement_id=requirement.id,
            requirement_no=requirement.requirement_no,
            status=requirement.status,
            requirement_version=requirement.version,
            building_id=requirement.building_id,
            building_name=building.building_name if building else None,
            applicant_name=requirement.applicant_name or "未登记员工",
            applicant_employee_no=requirement.applicant_employee_no,
            applicant_phone=requirement.applicant_phone,
            approver_employee_no=approval.approver_employee_no if approval else None,
            approver_name=approval.approver_name if approval else None,
            approver_phone=approval.approver_phone if approval else None,
            approval_comment=approval.comment if approval else None,
            approved_at=_utc_aware(approval.acted_at) if approval else None,
            product_name=requirement.product_name,
            product_full_name=requirement.product_full_name,
            brand=requirement.brand,
            model=requirement.model,
            specification=requirement.specification,
            quantity=requirement.quantity,
            unit=requirement.unit,
            supplier_name=requirement.supplier_name,
            unit_price=requirement.unit_price,
            total_amount=requirement.total_amount,
            currency=requirement.currency,
            order_id=order.id if order else None,
            order_no=order.order_no if order else None,
            order_version=order.version if order else None,
            purchaser_employee_no=order.purchaser_employee_no if order else None,
            purchaser_name=order.purchaser_name if order else None,
            purchaser_phone=order.purchaser_phone if order else None,
            purchasing_started_at=_utc_aware(order.purchasing_started_at) if order else None,
            quoted_at=_utc_aware(order.quoted_at) if order else None,
            contracted_at=_utc_aware(order.contracted_at) if order else None,
            received_at=_utc_aware(order.received_at) if order else None,
            completed_at=_utc_aware(order.completed_at) if order else None,
            updated_at=_utc_aware(order.updated_at if order else requirement.updated_at),
        )

    @staticmethod
    def _history(*, requirement, order, employee, from_status, to_status, remark, context, now):
        return PurchaseStatusHistory(
            requirement_id=requirement.id,
            order_id=order.id if order else None,
            from_status=from_status,
            to_status=to_status,
            operator_id=employee.id,
            operator_employee_no=employee.employee_no,
            operator_name=employee.name,
            operator_phone=employee.phone,
            remark=remark,
            changed_at=now,
            request_id=context.request_id,
            created_at=now,
        )

    @staticmethod
    def _idempotency(
        *, context, operation, request_hash, resource_type, resource_id, response, now
    ):
        return IdempotencyRecord(
            actor_code=context.actor.user_code,
            operation=operation,
            idempotency_key=context.idempotency_key,
            request_hash=request_hash,
            resource_type=resource_type,
            resource_id=resource_id,
            response_payload=response.model_dump(mode="json"),
            created_at=now,
        )

    @staticmethod
    async def _replay(repository, *, actor_code, operation, key, request_hash, model):
        record = await repository.get_idempotency_record(
            actor_code=actor_code, operation=operation, idempotency_key=key
        )
        if record is None:
            return None
        if record.request_hash != request_hash:
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT, "该操作标识已用于其他请求")
        return model.model_validate(record.response_payload)
