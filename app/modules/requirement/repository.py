"""采购申请草稿的数据访问层。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.requirement.models import (
    Employee,
    IdempotencyRecord,
    Product,
    ProductCategory,
    PurchaseOrder,
    PurchaseRequirement,
    PurchaseStatusHistory,
    Recommendation,
    Supplier,
)


class RequirementRepository:
    """隔离采购申请持久化操作与业务决策。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_employee_by_no(self, employee_no: str) -> Employee | None:
        return await self._session.scalar(
            select(Employee).where(
                Employee.employee_no == employee_no,
                Employee.status == "ACTIVE",
            )
        )

    async def get_requirement(self, requirement_id: int) -> PurchaseRequirement | None:
        return await self._session.get(PurchaseRequirement, requirement_id)

    async def get_requirement_for_update(self, requirement_id: int) -> PurchaseRequirement | None:
        return await self._session.scalar(
            select(PurchaseRequirement)
            .where(PurchaseRequirement.id == requirement_id)
            .with_for_update()
        )

    async def get_category(self, category_id: int) -> ProductCategory | None:
        return await self._session.get(ProductCategory, category_id)

    async def get_product(self, product_id: int) -> Product | None:
        return await self._session.get(Product, product_id)

    async def get_supplier(self, supplier_id: int) -> Supplier | None:
        return await self._session.get(Supplier, supplier_id)

    async def get_recommendation(self, recommendation_id: int) -> Recommendation | None:
        return await self._session.get(Recommendation, recommendation_id)

    async def list_owned_requirements(
        self,
        *,
        employee_id: int,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[PurchaseRequirement], int]:
        filters = [PurchaseRequirement.employee_id == employee_id]
        if status is not None:
            filters.append(PurchaseRequirement.status == status)
        total = await self._session.scalar(
            select(func.count(PurchaseRequirement.id)).where(*filters)
        )
        requirements = list(
            await self._session.scalars(
                select(PurchaseRequirement)
                .where(*filters)
                .order_by(PurchaseRequirement.updated_at.desc(), PurchaseRequirement.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return requirements, int(total or 0)

    async def list_completed_history(
        self,
        *,
        exclude_requirement_id: int,
        candidate_limit: int = 500,
    ) -> list[tuple[PurchaseOrder, PurchaseRequirement]]:
        result = await self._session.execute(
            select(PurchaseOrder, PurchaseRequirement)
            .join(PurchaseRequirement, PurchaseOrder.requirement_id == PurchaseRequirement.id)
            .where(
                PurchaseOrder.status == "COMPLETED",
                PurchaseRequirement.id != exclude_requirement_id,
            )
            .order_by(
                PurchaseOrder.received_at.desc(),
                PurchaseOrder.created_at.desc(),
                PurchaseOrder.id.desc(),
            )
            .limit(candidate_limit)
        )
        return list(result.tuples())

    async def get_idempotency_record(
        self,
        *,
        actor_code: str,
        operation: str,
        idempotency_key: str,
    ) -> IdempotencyRecord | None:
        return await self._session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.actor_code == actor_code,
                IdempotencyRecord.operation == operation,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )

    def add_requirement(self, requirement: PurchaseRequirement) -> None:
        self._session.add(requirement)

    def add_idempotency_record(self, record: IdempotencyRecord) -> None:
        self._session.add(record)

    def add_status_history(self, history: PurchaseStatusHistory) -> None:
        self._session.add(history)

    async def flush(self) -> None:
        await self._session.flush()
