import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.agent.context import AgentContext
from app.modules.agent.enums import AgentStage
from app.modules.agent.intent_recognizer import IntentCategory
from app.modules.agent.procurement.idempotency import update_idempotency_key
from app.modules.agent.procurement.protocols import RequirementBackendProtocol
from app.modules.agent.procurement.schemas import (
    DraftExtraction,
    ProcurementSessionState,
    RequirementDetail,
    RequirementDraftFields,
    RequirementSessionReference,
    RequirementSubmissionResult,
)
from app.modules.agent.state_machine import state_from_detail
from app.modules.agent.tools.base import AgentTool, ToolExecutionResult


def _detail_data(detail: RequirementDetail) -> dict[str, Any]:
    return detail.model_dump(mode="json")


def _reference(state: ProcurementSessionState) -> RequirementSessionReference:
    return RequirementSessionReference(
        requirement_id=state.requirement_id,
        requirement_no=state.requirement_no,
        status=state.status,
    )


def _with_recent(
    references: list[RequirementSessionReference],
    reference: RequirementSessionReference,
    *,
    exclude_id: int | None = None,
) -> list[RequirementSessionReference]:
    result = [
        item
        for item in references
        if item.requirement_id not in {reference.requirement_id, exclude_id}
    ]
    result.append(reference)
    return result[-10:]


def _new_draft_idempotency_key(
    conv_id: str,
    previous_requirement_id: int,
    payload: dict[str, Any],
) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"draft-{conv_id}-after-{previous_requirement_id}-{digest}"


class CreateRequirementDraftInput(RequirementDraftFields):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def has_business_information(self) -> "CreateRequirementDraftInput":
        values = self.model_dump(exclude_none=True)
        values.pop("session_id", None)
        values.pop("currency", None)
        if not values:
            raise ValueError("至少需要提供一项有效采购信息")
        return self


class RequirementReferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: int | None = Field(default=None, gt=0)


class SwitchActiveRequirementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: int = Field(gt=0)


class UpdateRequirementDraftInput(DraftExtraction):
    model_config = ConfigDict(extra="forbid")


class SubmitRequirementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: Literal[True]
    recommendation_id: int | None = Field(default=None, gt=0)


class CreateRequirementDraftTool(AgentTool):
    name = "create_requirement_draft"
    description = (
        "创建采购需求草稿。仅当当前会话还没有采购草稿，并且用户至少提供了一项真实采购信息时调用。"
        "需求人身份和创建时间由后端根据认证信息生成，不要把它们作为参数。"
    )
    input_model = CreateRequirementDraftInput
    is_write = True

    def __init__(self, backend: RequirementBackendProtocol) -> None:
        self._backend = backend

    async def execute(
        self,
        context: AgentContext,
        arguments: CreateRequirementDraftInput,
    ) -> ToolExecutionResult:
        if context.procurement_state is not None:
            return ToolExecutionResult(
                success=False,
                code="REQUIREMENT_ALREADY_EXISTS",
                message=(
                    f"当前会话已有采购草稿 {context.procurement_state.requirement_no}，"
                    "请查询或更新该草稿，不要重复创建。"
                ),
                data={"requirement_id": context.procurement_state.requirement_id},
            )

        payload = arguments.model_dump(exclude_none=True)
        payload["session_id"] = context.conv_id
        payload.setdefault("currency", "CNY")
        detail = await self._backend.create_draft(
            payload,
            actor=context.actor,
            request_id=context.request_id,
            idempotency_key=f"draft-{context.conv_id}-create",
        )
        context.procurement_state = state_from_detail(detail, scene=context.scene)
        return ToolExecutionResult(
            success=True,
            message=f"采购草稿 {detail.requirement_no} 已创建。",
            data=_detail_data(detail),
        )


class StartNewRequirementTool(AgentTool):
    name = "start_new_requirement"
    description = (
        "在当前聊天已有活动草稿时，创建一张内容不同的新采购草稿，并把原草稿保留到最近办理记录。"
        "用户明确说新建、另一个需求、新会话创建，或者明确描述了与当前草稿不同的新设备需求时调用。"
        "不要用它修改当前草稿。"
    )
    input_model = CreateRequirementDraftInput
    is_write = True

    def __init__(self, backend: RequirementBackendProtocol) -> None:
        self._backend = backend

    async def execute(
        self,
        context: AgentContext,
        arguments: CreateRequirementDraftInput,
    ) -> ToolExecutionResult:
        previous = context.procurement_state
        if previous is None:
            return ToolExecutionResult(
                success=False,
                code="NO_ACTIVE_REQUIREMENT",
                message="当前没有活动草稿，请使用create_requirement_draft创建第一张草稿。",
            )

        payload = arguments.model_dump(exclude_none=True)
        payload["session_id"] = context.conv_id
        payload.setdefault("currency", "CNY")
        detail = await self._backend.create_draft(
            payload,
            actor=context.actor,
            request_id=context.request_id,
            idempotency_key=_new_draft_idempotency_key(
                context.conv_id,
                previous.requirement_id,
                payload,
            ),
        )
        recent = _with_recent(previous.recent_requirements, _reference(previous))
        new_state = state_from_detail(detail, scene=context.scene)
        new_state.recent_requirements = recent
        context.procurement_state = new_state
        return ToolExecutionResult(
            success=True,
            message=(
                f"新采购草稿 {detail.requirement_no} 已创建并设为当前草稿；"
                f"原草稿 {previous.requirement_no} 已保留。"
            ),
            data={
                **_detail_data(detail),
                "previous_requirement": _reference(previous).model_dump(mode="json"),
            },
        )


class GetRequirementDetailTool(AgentTool):
    name = "get_requirement_detail"
    description = (
        "读取当前会话采购草稿的最新详情、状态、版本、缺失字段、冲突和风险。"
        "查看草稿、确认草稿或准备更新前应调用此工具。"
    )
    input_model = RequirementReferenceInput

    def __init__(self, backend: RequirementBackendProtocol) -> None:
        self._backend = backend

    async def execute(
        self,
        context: AgentContext,
        arguments: RequirementReferenceInput,
    ) -> ToolExecutionResult:
        state = context.procurement_state
        if state is None:
            return ToolExecutionResult(
                success=False,
                code="NO_ACTIVE_REQUIREMENT",
                message="当前会话还没有采购草稿，请先根据用户需求创建草稿。",
            )
        if arguments.requirement_id not in (None, state.requirement_id):
            return ToolExecutionResult(
                success=False,
                code="REQUIREMENT_SCOPE_MISMATCH",
                message="只能访问当前会话关联的采购草稿。",
            )

        detail = await self._backend.get_detail(
            state.requirement_id,
            actor=context.actor,
            request_id=context.request_id,
        )
        context.procurement_state = state_from_detail(detail, scene=context.scene, previous=state)
        return ToolExecutionResult(
            success=True,
            message=f"已读取采购草稿 {detail.requirement_no} 的最新详情。",
            data=_detail_data(detail),
        )


class SwitchActiveRequirementTool(AgentTool):
    name = "switch_active_requirement"
    description = (
        "把当前活动草稿切换为当前会话最近办理记录中的另一张草稿。"
        "当用户明确说切回某个需求编号或某张旧草稿时调用。"
    )
    input_model = SwitchActiveRequirementInput
    is_write = True

    def __init__(self, backend: RequirementBackendProtocol) -> None:
        self._backend = backend

    async def execute(
        self,
        context: AgentContext,
        arguments: SwitchActiveRequirementInput,
    ) -> ToolExecutionResult:
        current = context.procurement_state
        if current is None:
            return ToolExecutionResult(
                success=False,
                code="NO_ACTIVE_REQUIREMENT",
                message="当前会话没有可切换的采购草稿。",
            )
        target = next(
            (
                item
                for item in current.recent_requirements
                if item.requirement_id == arguments.requirement_id
            ),
            None,
        )
        if target is None:
            return ToolExecutionResult(
                success=False,
                code="REQUIREMENT_SCOPE_MISMATCH",
                message="目标草稿不在当前会话的最近办理记录中，不能切换。",
            )

        detail = await self._backend.get_detail(
            target.requirement_id,
            actor=context.actor,
            request_id=context.request_id,
        )
        recent = _with_recent(
            current.recent_requirements,
            _reference(current),
            exclude_id=target.requirement_id,
        )
        switched = state_from_detail(detail, scene=context.scene)
        switched.recent_requirements = recent
        context.procurement_state = switched
        return ToolExecutionResult(
            success=True,
            message=f"已切换到采购草稿 {detail.requirement_no}。",
            data=_detail_data(detail),
        )


class UpdateRequirementDraftTool(AgentTool):
    name = "update_requirement_draft"
    description = (
        "更新当前会话的采购需求草稿。changes只包含用户本轮新增或明确修改的字段；"
        "未提及字段不要传入，普通null不会清空字段；只有用户明确要求清空时才放入clear_fields。"
        "工具会自动读取最新详情和version，不要传version。"
    )
    input_model = UpdateRequirementDraftInput
    is_write = True

    def __init__(self, backend: RequirementBackendProtocol) -> None:
        self._backend = backend

    async def execute(
        self,
        context: AgentContext,
        arguments: UpdateRequirementDraftInput,
    ) -> ToolExecutionResult:
        state = context.procurement_state
        if state is None:
            return ToolExecutionResult(
                success=False,
                code="NO_ACTIVE_REQUIREMENT",
                message="当前会话还没有采购草稿，不能执行更新。",
            )

        current = await self._backend.get_detail(
            state.requirement_id,
            actor=context.actor,
            request_id=context.request_id,
        )
        context.procurement_state = state_from_detail(current, scene=context.scene, previous=state)
        if current.status != "DRAFT":
            return ToolExecutionResult(
                success=False,
                code="REQUIREMENT_NOT_EDITABLE",
                message=(
                    f"采购需求 {current.requirement_no} 当前状态为 {current.status}，"
                    "不能继续修改草稿。"
                ),
                data=_detail_data(current),
            )

        patch = arguments.to_patch()
        patch.pop("session_id", None)
        if not patch:
            return ToolExecutionResult(
                success=False,
                code="EMPTY_UPDATE",
                message="没有识别到用户本轮新增、修改或明确清空的采购字段。",
                data=_detail_data(current),
            )

        payload = {"version": current.version, **patch}
        detail = await self._backend.update_draft(
            current.requirement_id,
            payload,
            actor=context.actor,
            request_id=context.request_id,
            idempotency_key=update_idempotency_key(current.requirement_id, current.version, patch),
        )
        context.procurement_state = state_from_detail(
            detail,
            scene=context.scene,
            previous=context.procurement_state,
        )
        return ToolExecutionResult(
            success=True,
            message=f"采购草稿 {detail.requirement_no} 已更新。",
            data=_detail_data(detail),
        )


class SubmitRequirementTool(AgentTool):
    name = "submit_requirement"
    description = (
        "把当前员工的完整采购草稿正式提交审批。仅当用户本轮明确要求确认提交时调用；"
        "工具会先读取数据库最新详情和version，不要把草稿状态或版本作为参数。"
    )
    input_model = SubmitRequirementInput
    is_write = True

    def __init__(self, backend: RequirementBackendProtocol) -> None:
        self._backend = backend

    async def execute(
        self,
        context: AgentContext,
        arguments: SubmitRequirementInput,
    ) -> ToolExecutionResult:
        if context.intent != IntentCategory.CONFIRM_SUBMISSION:
            return ToolExecutionResult(
                success=False,
                code="EXPLICIT_CONFIRMATION_REQUIRED",
                message="只有员工本轮明确确认提交审批时，才能执行正式提交。",
            )

        state = context.procurement_state
        if state is None:
            return ToolExecutionResult(
                success=False,
                code="NO_ACTIVE_REQUIREMENT",
                message="当前会话没有可提交的采购草稿。",
            )

        current = await self._backend.get_detail(
            state.requirement_id,
            actor=context.actor,
            request_id=context.request_id,
        )
        context.procurement_state = state_from_detail(
            current,
            scene=context.scene,
            previous=state,
        )
        if current.status != "DRAFT":
            return ToolExecutionResult(
                success=False,
                code="REQUIREMENT_NOT_SUBMITTABLE",
                message=(
                    f"采购需求 {current.requirement_no} 当前状态为 {current.status}，"
                    "不能再次提交审批。"
                ),
                data=_detail_data(current),
            )
        if current.missing_fields or current.conflicts:
            return ToolExecutionResult(
                success=False,
                code="REQUIREMENT_INCOMPLETE",
                message="采购草稿仍有缺失字段或冲突，尚未执行正式提交。",
                data=_detail_data(current),
            )

        result = await self._backend.submit(
            current.requirement_id,
            {
                "version": current.version,
                "confirmed": arguments.confirmed,
                "recommendation_id": arguments.recommendation_id,
            },
            actor=context.actor,
            request_id=context.request_id,
            idempotency_key=f"submit-{current.requirement_id}-v{current.version}",
        )
        self._apply_submission(context, result)
        return ToolExecutionResult(
            success=True,
            message=f"采购申请 {result.requirement_no} 已正式提交审批。",
            data=result.model_dump(mode="json"),
        )

    @staticmethod
    def _apply_submission(
        context: AgentContext,
        result: RequirementSubmissionResult,
    ) -> None:
        state = context.procurement_state
        if state is None:
            return
        state.status = result.status
        state.version = result.version
        state.stage = AgentStage.SUBMITTED
        state.pending_action = None
