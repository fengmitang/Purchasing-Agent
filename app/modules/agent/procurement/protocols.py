from typing import Any, Protocol

from app.modules.agent.procurement.schemas import RequirementDetail
from app.shared.identity import CurrentUser


class RequirementBackendProtocol(Protocol):
    async def create_draft(
        self,
        payload: dict[str, Any],
        *,
        actor: CurrentUser,
        request_id: str,
        idempotency_key: str,
    ) -> RequirementDetail: ...

    async def get_detail(
        self,
        requirement_id: int,
        *,
        actor: CurrentUser,
        request_id: str,
    ) -> RequirementDetail: ...

    async def update_draft(
        self,
        requirement_id: int,
        payload: dict[str, Any],
        *,
        actor: CurrentUser,
        request_id: str,
        idempotency_key: str,
    ) -> RequirementDetail: ...
