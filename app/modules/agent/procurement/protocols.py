from typing import Any, Protocol

from app.modules.agent.procurement.schemas import (
    HistoricalSupplierRecommendationResult,
    RequirementDetail,
    RequirementListResult,
    RequirementSubmissionResult,
)
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

    async def submit(
        self,
        requirement_id: int,
        payload: dict[str, Any],
        *,
        actor: CurrentUser,
        request_id: str,
        idempotency_key: str,
    ) -> RequirementSubmissionResult: ...

    async def cancel_draft(
        self,
        requirement_id: int,
        payload: dict[str, Any],
        *,
        actor: CurrentUser,
        request_id: str,
        idempotency_key: str,
    ) -> RequirementDetail: ...

    async def search_historical_suppliers(
        self,
        payload: dict[str, Any],
        *,
        actor: CurrentUser,
        request_id: str,
    ) -> HistoricalSupplierRecommendationResult: ...

    async def list_mine(
        self,
        *,
        actor: CurrentUser,
        request_id: str,
        status: str | None,
        page: int,
        page_size: int,
    ) -> RequirementListResult: ...
