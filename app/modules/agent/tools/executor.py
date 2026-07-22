import hashlib
import json
import logging
from typing import Any

from pydantic import ValidationError

from app.modules.agent.context import AgentContext
from app.modules.agent.procurement.backend_client import ProcurementBackendError
from app.modules.agent.tools.base import ToolExecutionResult
from app.modules.agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    TERMINAL_ERROR_CODES = {
        "UNAUTHENTICATED",
        "FORBIDDEN",
        "BACKEND_NOT_CONFIGURED",
        "BACKEND_UNAVAILABLE",
        "INVALID_BACKEND_RESPONSE",
    }

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(
        self,
        *,
        context: AgentContext,
        tool_name: str,
        raw_arguments: dict[str, Any],
        allowed_names: set[str],
        executed_writes: set[str],
    ) -> ToolExecutionResult:
        if tool_name not in allowed_names:
            return ToolExecutionResult(
                success=False,
                code="TOOL_NOT_ALLOWED",
                message=f"当前采购场景不允许调用工具：{tool_name}",
            )

        tool = self._registry.get(tool_name)
        if tool is None:
            return ToolExecutionResult(
                success=False,
                code="TOOL_NOT_FOUND",
                message=f"工具不存在：{tool_name}",
            )

        try:
            arguments = tool.input_model.model_validate(raw_arguments)
        except ValidationError as exc:
            errors = []
            for item in exc.errors(include_url=False):
                normalized = dict(item)
                if "ctx" in normalized:
                    normalized["ctx"] = {
                        key: str(value) for key, value in normalized["ctx"].items()
                    }
                errors.append(normalized)
            return ToolExecutionResult(
                success=False,
                code="INVALID_TOOL_ARGUMENTS",
                message="工具参数不符合接口约束，请根据字段说明重新调用。",
                data={"errors": errors},
            )

        fingerprint = self._fingerprint(tool_name, arguments.model_dump(mode="json"))
        if tool.is_write and fingerprint in executed_writes:
            return ToolExecutionResult(
                success=False,
                code="DUPLICATE_WRITE_BLOCKED",
                message="本轮已经执行过完全相同的写操作，未再次写入。",
            )

        try:
            result = await tool.execute(context, arguments)
            if tool.is_write and result.success:
                executed_writes.add(fingerprint)
            logger.info(
                "采购Agent工具调用 tool=%s success=%s code=%s request_id=%s",
                tool_name,
                result.success,
                result.code,
                context.request_id,
            )
            return result
        except ProcurementBackendError as exc:
            logger.warning(
                "采购后端工具失败 tool=%s code=%s request_id=%s",
                tool_name,
                exc.code,
                context.request_id,
            )
            return ToolExecutionResult(
                success=False,
                code=exc.code,
                message=self._safe_backend_message(exc),
                data={"details": exc.details},
                terminal=exc.code in self.TERMINAL_ERROR_CODES,
            )
        except Exception:
            logger.exception(
                "采购Agent工具异常 tool=%s request_id=%s",
                tool_name,
                context.request_id,
            )
            return ToolExecutionResult(
                success=False,
                code="TOOL_EXECUTION_FAILED",
                message="工具执行失败，本轮没有完成写入，请稍后重试。",
                terminal=True,
            )

    @staticmethod
    def _fingerprint(tool_name: str, arguments: dict[str, Any]) -> str:
        canonical = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(f"{tool_name}:{canonical}".encode()).hexdigest()

    @staticmethod
    def _safe_backend_message(error: ProcurementBackendError) -> str:
        messages = {
            "UNAUTHENTICATED": "登录状态无效，请重新登录后继续。",
            "FORBIDDEN": "你没有权限访问或修改这张采购草稿。",
            "RESOURCE_NOT_FOUND": "采购草稿不存在或当前用户不可访问。",
            "STATE_CONFLICT": "当前采购状态不允许执行这项操作。",
            "VERSION_CONFLICT": "采购草稿已被更新，请重新查询最新详情后再决定是否修改。",
            "IDEMPOTENCY_CONFLICT": "本次写入与已有幂等请求冲突，未重复写入。",
            "BACKEND_NOT_CONFIGURED": "采购后端地址尚未配置，暂时无法保存草稿。",
            "BACKEND_UNAVAILABLE": "采购后端暂时不可用，本轮信息没有写入。",
            "INVALID_BACKEND_RESPONSE": "采购后端返回格式异常，本轮信息没有写入。",
        }
        return messages.get(error.code, error.message or "采购后端处理失败。")
