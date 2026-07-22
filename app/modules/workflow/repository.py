"""楼长审批和采购执行的数据访问层。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import Building
from app.modules.requirement.models import (
    Employee,
    IdempotencyRecord,
    PurchaseApproval,
    PurchaseOrder,
    PurchaseRequirement,
)


class WorkflowRepository:
    """封装工作流查询和持久化，不在此层决定权限。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_employee_by_no(self, employee_no: str) -> Employee | None:
        return await self._session.scalar(
            select(Employee).where(
                Employee.employee_no == employee_no,
                Employee.status == "ACTIVE",
            )
        )

    async def list_buildings(self) -> list[Building]:
        return list(
            await self._session.scalars(
                select(Building)
                .where(Building.status == "ACTIVE")
                .order_by(Building.building_code, Building.id)
            )
        )

    async def get_building(self, building_id: int) -> Building | None:
        return await self._session.scalar(
            select(Building).where(Building.id == building_id, Building.status == "ACTIVE")
        )

    async def list_approval_tasks(
        self,
        *,
        building_ids: frozenset[int],
        approver_id: int,
        view: str,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple[PurchaseRequirement, Building, PurchaseApproval | None]], int]:
        filters = [PurchaseRequirement.building_id.in_(building_ids)]
        if view == "pending":
            filters.append(PurchaseRequirement.status == "PENDING_APPROVAL")
            approval_join = PurchaseApproval.requirement_id == -1
            order_by = (PurchaseRequirement.submitted_at.asc(), PurchaseRequirement.id.asc())
        else:
            filters.append(PurchaseApproval.approver_id == approver_id)
            approval_join = PurchaseApproval.requirement_id == PurchaseRequirement.id
            order_by = (PurchaseApproval.acted_at.desc(), PurchaseApproval.id.desc())
        total = await self._session.scalar(
            select(func.count(PurchaseRequirement.id))
            .outerjoin(PurchaseApproval, approval_join)
            .where(*filters)
        )
        rows = await self._session.execute(
            select(PurchaseRequirement, Building, PurchaseApproval)
            .join(Building, Building.id == PurchaseRequirement.building_id)
            .outerjoin(PurchaseApproval, approval_join)
            .where(*filters)
            .order_by(*order_by)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.tuples()), int(total or 0)

    async def get_approval_for_actor(
        self, requirement_id: int, approver_id: int
    ) -> PurchaseApproval | None:
        return await self._session.scalar(
            select(PurchaseApproval)
            .where(
                PurchaseApproval.requirement_id == requirement_id,
                PurchaseApproval.approver_id == approver_id,
            )
            .order_by(PurchaseApproval.acted_at.desc(), PurchaseApproval.id.desc())
        )

    async def get_requirement_with_building(
        self, requirement_id: int
    ) -> tuple[PurchaseRequirement, Building] | None:
        row = await self._session.execute(
            select(PurchaseRequirement, Building)
            .join(Building, Building.id == PurchaseRequirement.building_id)
            .where(PurchaseRequirement.id == requirement_id)
        )
        return row.tuples().first()

    async def get_requirement_for_update(self, requirement_id: int) -> PurchaseRequirement | None:
        return await self._session.scalar(
            select(PurchaseRequirement)
            .where(PurchaseRequirement.id == requirement_id)
            .with_for_update()
        )

    async def list_procurement_tasks(
        self, *, page: int, page_size: int
    ) -> tuple[
        list[
            tuple[
                PurchaseRequirement,
                Building | None,
                PurchaseOrder | None,
                PurchaseApproval | None,
            ]
        ],
        int,
    ]:
        statuses = ("APPROVED", "PURCHASING", "QUOTED", "CONTRACTED", "COMPLETED")
        latest_approval_id = (
            select(func.max(PurchaseApproval.id))
            .where(PurchaseApproval.requirement_id == PurchaseRequirement.id)
            .correlate(PurchaseRequirement)
            .scalar_subquery()
        )
        total = await self._session.scalar(
            select(func.count(PurchaseRequirement.id)).where(
                PurchaseRequirement.status.in_(statuses)
            )
        )
        rows = await self._session.execute(
            select(PurchaseRequirement, Building, PurchaseOrder, PurchaseApproval)
            .outerjoin(Building, Building.id == PurchaseRequirement.building_id)
            .outerjoin(PurchaseOrder, PurchaseOrder.requirement_id == PurchaseRequirement.id)
            .outerjoin(PurchaseApproval, PurchaseApproval.id == latest_approval_id)
            .where(PurchaseRequirement.status.in_(statuses))
            .order_by(PurchaseRequirement.updated_at.desc(), PurchaseRequirement.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.tuples()), int(total or 0)

    async def get_latest_approval(self, requirement_id: int) -> PurchaseApproval | None:
        return await self._session.scalar(
            select(PurchaseApproval)
            .where(PurchaseApproval.requirement_id == requirement_id)
            .order_by(PurchaseApproval.acted_at.desc(), PurchaseApproval.id.desc())
        )

    async def get_order_by_requirement(self, requirement_id: int) -> PurchaseOrder | None:
        return await self._session.scalar(
            select(PurchaseOrder).where(PurchaseOrder.requirement_id == requirement_id)
        )

    async def get_order_for_update(self, order_id: int) -> PurchaseOrder | None:
        return await self._session.scalar(
            select(PurchaseOrder).where(PurchaseOrder.id == order_id).with_for_update()
        )

    async def get_requirement(self, requirement_id: int) -> PurchaseRequirement | None:
        return await self._session.get(PurchaseRequirement, requirement_id)

    async def get_idempotency_record(
        self, *, actor_code: str, operation: str, idempotency_key: str
    ) -> IdempotencyRecord | None:
        return await self._session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.actor_code == actor_code,
                IdempotencyRecord.operation == operation,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )

    def add(self, record: object) -> None:
        self._session.add(record)

    async def flush(self) -> None:
        await self._session.flush()
