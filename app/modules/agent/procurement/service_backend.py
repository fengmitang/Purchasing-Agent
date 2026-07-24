from typing import Any

from pydantic import ValidationError

from app.modules.agent.procurement.backend_client import ProcurementBackendError
from app.modules.agent.procurement.schemas import (
    HistoricalSupplierRecommendationResult,
    RequirementDetail,
    RequirementListResult,
    RequirementSubmissionResult,
    RequirementSummary,
)
from app.modules.requirement.schemas import (
    CancelRequirementDraft,
    CreateRequirementDraft,
    HistoricalSupplierQuery,
    SubmitRequirement,
    UpdateRequirementDraft,
)
from app.modules.requirement.service import RequirementService
from app.shared.errors import DomainError
from app.shared.identity import AuditContext, CurrentUser


class RequirementServiceBackend:
    """Internal Agent adapter that preserves the RequirementService security boundary."""

    def __init__(self, service: RequirementService) -> None:
        self._service = service

    async def create_draft(
        self,
        payload: dict[str, Any],
        *,
        actor: CurrentUser,
        request_id: str,
        idempotency_key: str,
    ) -> RequirementDetail:
        try:
            command = CreateRequirementDraft.model_validate(payload)
        except ValidationError as exc:
            raise self._validation_error(exc) from exc
        try:
            detail = await self._service.create_draft(
                command,
                AuditContext(
                    actor=actor,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                ),
            )
        except DomainError as exc:
            raise self._backend_error(exc) from exc
        return RequirementDetail.model_validate(detail.model_dump(mode="json"))

    async def get_detail(
        self,
        requirement_id: int,
        *,
        actor: CurrentUser,
        request_id: str,
    ) -> RequirementDetail:
        del request_id
        try:
            detail = await self._service.get_detail(requirement_id, actor)
        except DomainError as exc:
            raise self._backend_error(exc) from exc
        return RequirementDetail.model_validate(detail.model_dump(mode="json"))

    async def update_draft(
        self,
        requirement_id: int,
        payload: dict[str, Any],
        *,
        actor: CurrentUser,
        request_id: str,
        idempotency_key: str,
    ) -> RequirementDetail:
        try:
            command = UpdateRequirementDraft.model_validate(payload)
        except ValidationError as exc:
            raise self._validation_error(exc) from exc
        try:
            detail = await self._service.update_draft(
                requirement_id,
                command,
                AuditContext(
                    actor=actor,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                ),
            )
        except DomainError as exc:
            raise self._backend_error(exc) from exc
        return RequirementDetail.model_validate(detail.model_dump(mode="json"))

    async def submit(
        self,
        requirement_id: int,
        payload: dict[str, Any],
        *,
        actor: CurrentUser,
        request_id: str,
        idempotency_key: str,
    ) -> RequirementSubmissionResult:
        try:
            command = SubmitRequirement.model_validate(payload)
            result = await self._service.submit(
                requirement_id,
                command,
                AuditContext(
                    actor=actor,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                ),
            )
        except ValidationError as exc:
            raise self._validation_error(exc) from exc
        except DomainError as exc:
            raise self._backend_error(exc) from exc
        return RequirementSubmissionResult.model_validate(result.model_dump(mode="json"))

    async def cancel_draft(
        self,
        requirement_id: int,
        payload: dict[str, Any],
        *,
        actor: CurrentUser,
        request_id: str,
        idempotency_key: str,
    ) -> RequirementDetail:
        try:
            command = CancelRequirementDraft.model_validate(payload)
            detail = await self._service.cancel_draft(
                requirement_id,
                command,
                AuditContext(
                    actor=actor,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                ),
            )
        except ValidationError as exc:
            raise self._validation_error(exc) from exc
        except DomainError as exc:
            raise self._backend_error(exc) from exc
        return RequirementDetail.model_validate(detail.model_dump(mode="json"))

    async def search_historical_suppliers(
        self,
        payload: dict[str, Any],
        *,
        actor: CurrentUser,
        request_id: str,
    ) -> HistoricalSupplierRecommendationResult:
        del request_id
        try:
            query = HistoricalSupplierQuery.model_validate(payload)
            result = await self._service.search_historical_suppliers(query, actor)
        except ValidationError as exc:
            raise self._validation_error(exc) from exc
        except DomainError as exc:
            raise self._backend_error(exc) from exc
        return HistoricalSupplierRecommendationResult.model_validate(result.model_dump(mode="json"))

    async def list_mine(
        self,
        *,
        actor: CurrentUser,
        request_id: str,
        status: str | None,
        page: int,
        page_size: int,
    ) -> RequirementListResult:
        del request_id
        try:
            items, total = await self._service.list_mine(
                actor=actor,
                status=status,
                page=page,
                page_size=page_size,
            )
        except DomainError as exc:
            raise self._backend_error(exc) from exc
        return RequirementListResult(
            items=[
                RequirementSummary.model_validate(item.model_dump(mode="json")) for item in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def _backend_error(exc: DomainError) -> ProcurementBackendError:
        status_by_code = {
            "UNAUTHENTICATED": 401,
            "FORBIDDEN": 403,
            "RESOURCE_NOT_FOUND": 404,
            "VALIDATION_ERROR": 422,
        }
        code = str(exc.code.value if hasattr(exc.code, "value") else exc.code)
        return ProcurementBackendError(
            code,
            exc.message,
            status_code=status_by_code.get(code, 409),
            details=list(exc.details),
        )

    @staticmethod
    def _validation_error(exc: ValidationError) -> ProcurementBackendError:
        details = [
            {
                "field": ".".join(str(part) for part in error["loc"]),
                "reason": error["type"],
            }
            for error in exc.errors(include_url=False)
        ]
        return ProcurementBackendError(
            "VALIDATION_ERROR",
            "采购工具参数未通过后端校验",
            status_code=422,
            details=details,
        )
