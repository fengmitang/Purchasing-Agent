from typing import Any

import httpx

from app.modules.agent.procurement.schemas import RequirementDetail


class ProcurementBackendError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 500,
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []


class ProcurementBackendClient:
    """只封装已约定的创建草稿、增量更新和详情查询接口。"""

    def __init__(
        self,
        base_url: str,
        *,
        service_token: str | None = None,
        timeout_seconds: float = 15.0,
        transport: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def create_draft(
        self,
        payload: dict[str, Any],
        *,
        authorization: str | None,
        request_id: str,
        idempotency_key: str,
    ) -> RequirementDetail:
        data = await self._request(
            "POST",
            "/api/v1/purchase-requirements/drafts",
            payload=payload,
            authorization=authorization,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        return RequirementDetail.model_validate(data)

    async def get_detail(
        self,
        requirement_id: int,
        *,
        authorization: str | None,
        request_id: str,
    ) -> RequirementDetail:
        data = await self._request(
            "GET",
            f"/api/v1/purchase-requirements/{requirement_id}",
            authorization=authorization,
            request_id=request_id,
        )
        return RequirementDetail.model_validate(data)

    async def update_draft(
        self,
        requirement_id: int,
        payload: dict[str, Any],
        *,
        authorization: str | None,
        request_id: str,
        idempotency_key: str,
    ) -> RequirementDetail:
        data = await self._request(
            "PATCH",
            f"/api/v1/purchase-requirements/{requirement_id}",
            payload=payload,
            authorization=authorization,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        return RequirementDetail.model_validate(data)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        authorization: str | None,
        request_id: str,
        idempotency_key: str | None = None,
    ) -> Any:
        if not self.base_url:
            raise ProcurementBackendError(
                "BACKEND_NOT_CONFIGURED",
                "采购后端地址未配置。",
                status_code=503,
            )

        headers = {"X-Request-ID": request_id}
        auth = authorization or self.service_token
        if auth:
            headers["Authorization"] = (
                auth if auth.lower().startswith("bearer ") else f"Bearer {auth}"
            )
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        try:
            client_options: dict[str, Any] = {
                "base_url": self.base_url,
                "timeout": self.timeout_seconds,
            }
            if self.transport is not None:
                client_options["transport"] = self.transport
            async with httpx.AsyncClient(**client_options) as client:
                response = await client.request(method, path, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ProcurementBackendError(
                "BACKEND_UNAVAILABLE",
                "采购后端暂时不可用，请稍后重试。",
                status_code=503,
            ) from exc

        body: dict[str, Any]
        try:
            body = response.json()
        except ValueError:
            body = {}

        if response.is_error:
            error = body.get("error") if isinstance(body, dict) else None
            error = error if isinstance(error, dict) else {}
            raise ProcurementBackendError(
                str(error.get("code") or "BACKEND_ERROR"),
                str(error.get("message") or "采购后端处理失败。"),
                status_code=response.status_code,
                details=error.get("details") if isinstance(error.get("details"), list) else [],
            )

        if not isinstance(body, dict) or "data" not in body:
            raise ProcurementBackendError(
                "INVALID_BACKEND_RESPONSE",
                "采购后端返回格式不符合契约。",
                status_code=502,
            )
        return body["data"]
