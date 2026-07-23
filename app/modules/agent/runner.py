# ruff: noqa: E501

import json
import logging
import time
from typing import Any

from app.modules.agent.context import AgentContext
from app.modules.agent.enums import AgentScene, AgentStage
from app.modules.agent.intent_recognizer import IntentCategory
from app.modules.agent.model import AgentModelProtocol
from app.modules.agent.result import AgentHandleResult
from app.modules.agent.tools.executor import ToolExecutor
from app.modules.agent.tools.registry import ToolRegistry
from app.modules.agent.trace import AgentTrace

logger = logging.getLogger(__name__)


class ProcurementAgentRunner:
    FALSE_SUBMISSION_PHRASES = (
        "提交成功",
        "已成功提交",
        "已经提交",
        "已提交审批",
        "提交完成",
    )
    FALSE_CANCELLATION_PHRASES = (
        "取消成功",
        "已成功取消",
        "已经取消",
        "已撤销",
        "撤销成功",
    )

    def __init__(
        self,
        model: AgentModelProtocol,
        registry: ToolRegistry,
        executor: ToolExecutor,
        *,
        skill_manager: Any | None = None,
        max_iterations: int = 6,
    ) -> None:
        self._model = model
        self._registry = registry
        self._executor = executor
        self._skill_manager = skill_manager
        self._max_iterations = max_iterations

    async def run(self, context: AgentContext) -> AgentHandleResult:
        trace = AgentTrace(context.request_id, context.conv_id, context.user_id)
        messages = self._initial_messages(context)
        executed_writes: set[str] = set()
        initial_allowed_names = self._allowed_tools(context)
        trace.emit(
            "agent.context.ready",
            intent=context.intent.value,
            scene=context.scene.value,
            stage=context.stage.value,
            has_requirement=context.procurement_state is not None,
            allowed_tools=sorted(initial_allowed_names),
            history_messages=len(context.history),
        )

        for iteration in range(1, self._max_iterations + 1):
            allowed_names = self._allowed_tools(context)
            tools = self._registry.schemas(allowed_names)
            system = self._system_prompt(context)
            model_started = time.monotonic()
            trace.emit(
                "model.requested",
                iteration=iteration,
                message_count=len(messages),
                allowed_tools=sorted(allowed_names),
            )
            try:
                decision = await self._model.complete(
                    system=system,
                    messages=messages,
                    tools=tools,
                )
            except Exception as exc:
                logger.exception(
                    "采购Agent模型调用失败 iteration=%s request_id=%s",
                    iteration,
                    context.request_id,
                )
                trace.emit(
                    "model.failed",
                    iteration=iteration,
                    duration_ms=round((time.monotonic() - model_started) * 1000, 2),
                )
                raise RuntimeError("agent model unavailable") from exc

            trace.emit(
                "model.completed",
                iteration=iteration,
                duration_ms=round((time.monotonic() - model_started) * 1000, 2),
                tool_calls=[call.name for call in decision.tool_calls],
                response_chars=len(decision.text),
            )

            if not decision.tool_calls:
                response = decision.text or "请补充本次采购需求的设备、数量、原因或使用地点。"
                response = self._guard_submission_claim(context, response)
                trace.emit("agent.completed", iteration=iteration, reason="model_response")
                return self._result(context, response, trace)

            assistant_content = decision.assistant_content or [
                {
                    "type": "tool_use",
                    "id": call.id,
                    "name": call.name,
                    "input": call.arguments,
                }
                for call in decision.tool_calls
            ]
            messages.append({"role": "assistant", "content": assistant_content})

            tool_result_blocks: list[dict[str, Any]] = []
            terminal_message: str | None = None
            for call in decision.tool_calls:
                tool_started = time.monotonic()
                trace.emit(
                    "tool.requested",
                    iteration=iteration,
                    tool=call.name,
                    argument_fields=sorted(call.arguments.keys()),
                )
                result = await self._executor.execute(
                    context=context,
                    tool_name=call.name,
                    raw_arguments=call.arguments,
                    allowed_names=allowed_names,
                    executed_writes=executed_writes,
                )
                trace.emit(
                    "tool.completed",
                    iteration=iteration,
                    tool=call.name,
                    success=result.success,
                    code=result.code,
                    terminal=result.terminal,
                    duration_ms=round((time.monotonic() - tool_started) * 1000, 2),
                    requirement_id=(
                        context.procurement_state.requirement_id
                        if context.procurement_state is not None
                        else None
                    ),
                )
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "is_error": not result.success,
                        "content": result.model_dump_json(),
                    }
                )
                if result.terminal:
                    terminal_message = result.message

            messages.append({"role": "user", "content": tool_result_blocks})
            if terminal_message:
                trace.emit("agent.completed", iteration=iteration, reason="terminal_tool_error")
                return self._result(context, terminal_message, trace)

        trace.emit("agent.limit_reached", max_iterations=self._max_iterations)
        return self._result(
            context,
            "本轮已经达到最大工具调用次数。为避免重复写入，流程已暂停，请明确说明下一步需要补充、修改还是查看草稿。",
            trace,
        )

    def _allowed_tools(self, context: AgentContext) -> set[str]:
        if context.scene == AgentScene.GENERAL_QUERY:
            return set()
        if context.intent == IntentCategory.LIST_REQUIREMENTS:
            return {"list_my_requirements"}
        if context.intent == IntentCategory.QUERY_STATUS:
            return (
                {"get_requirement_detail"}
                if context.procurement_state is not None
                else {"list_my_requirements"}
            )
        if context.intent == IntentCategory.VIEW_REQUIREMENT:
            return {"get_requirement_detail"}
        if context.intent == IntentCategory.CONFIRM_SUBMISSION:
            if context.procurement_state is None:
                return set()
            return {
                "get_requirement_detail",
                "update_requirement_draft",
                "submit_requirement",
            }
        if context.intent == IntentCategory.CANCEL_REQUIREMENT:
            if context.procurement_state is None:
                return set()
            return {"get_requirement_detail", "cancel_requirement"}
        if context.intent == IntentCategory.SEARCH_HISTORICAL_SUPPLIERS:
            if context.procurement_state is None:
                return set()
            return {"get_requirement_detail", "search_historical_suppliers"}
        if context.procurement_state is None:
            return {"create_requirement_draft"}
        return {
            "get_requirement_detail",
            "update_requirement_draft",
            "start_new_requirement",
            "switch_active_requirement",
        }

    def _initial_messages(self, context: AgentContext) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for item in context.history[-12:]:
            role = str(item.get("role", ""))
            content = str(item.get("content", "")).strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        if (
            not messages
            or messages[-1].get("role") != "user"
            or messages[-1].get("content") != context.message
        ):
            messages.append({"role": "user", "content": context.message})
        return messages

    def _system_prompt(self, context: AgentContext) -> str:
        if context.scene == AgentScene.GENERAL_QUERY:
            return (
                "你是数据中心采购系统的内部员工助手。可以进行简洁的通用中文对话，"
                "但当前场景没有任何工具，不得声称已查询实时数据、内部数据、价格、库存或状态。"
                "不知道的事实明确说明不知道；需要办理采购时提示用户描述采购需求。"
            )
        state = (
            context.procurement_state.model_dump(mode="json")
            if context.procurement_state is not None
            else None
        )
        skill_text = self._procurement_skills()
        return f"""
你是数据中心采购需求Agent。你的目标是通过多轮对话和受控工具，帮助当前用户形成真实、可追踪的采购需求草稿。

你可以根据当前消息、历史对话、会话状态和工具执行结果自主决定下一步：调用工具、继续调用其他工具，或者向用户追问。

硬性规则：
1. 后端工具结果是草稿状态、字段、缺失项、冲突、风险、需求人和时间的唯一事实来源。
2. 当前没有草稿且用户提供了至少一项采购信息时，调用create_requirement_draft；不要只在内存中假装创建。
3. 当前已有草稿时不得再次创建；查看或修改前优先调用get_requirement_detail。
4. 用户明确说“新建一条”“另一个需求”“新会话创建”，或明确描述了与当前草稿不同的新设备采购时，调用start_new_requirement；原草稿必须保留，不能把新设备覆盖到旧草稿。
5. 用户要求切回最近办理的某张草稿时，调用switch_active_requirement。只能使用会话状态recent_requirements中的ID。
6. 无法判断用户是在修改当前草稿还是发起新需求时，先问清楚，不要擅自覆盖或新建。
7. update_requirement_draft的changes只放用户本轮新增或明确修改的字段；没有提到的字段不要传，普通null不能清空字段。
8. 只有用户明确说清空或删除某字段时，才把字段名放进clear_fields。
9. 提交审批必填字段仅包括application_reason、application_location、product_name、quantity。
10. 只能根据后端返回的missing_fields追问，最多两个。禁止通过检查工具结果中值为null的字段自行推断缺失项；提交完整性只以missing_fields为准。category_id、category_name、device_type、product_id、product_full_name、brand、model、specification、unit、supplier_id、supplier_name、unit_price、currency均为选填，不得主动追问或阻止提交。
11. 如果missing_fields为空且conflicts为空，不得继续追问任何采购字段，应明确告诉用户：“当前提交所需信息已经完整，可以提交审批。”conflicts必须请用户确认；warnings需要明确提示。
12. 用户明确表示“不知道”“暂不提供”“不用填”或“先保存”时，通过update_requirement_draft.defer_fields记录；不得继续追问对应选填字段。若deferred_fields中的字段仍被后端列入missing_fields，只说明草稿可保留但不能提交。
13. 不得编造需求人、时间、产品、型号、价格、供应商、历史记录、编号或状态。需求人来自认证信息，时间来自后端。
14. 用户本轮明确确认提交时，先处理本轮新增字段，再读取最新详情，最后调用submit_requirement；缺失、冲突、更新失败或查询失败时不得提交。
15. 用户明确确认取消且提供原因时，读取最新详情后调用cancel_requirement；缺少原因时只追问原因。
16. 历史推荐只调用search_historical_suppliers并忠实展示结果，不得自动选中或修改供应商。
17. list_my_requirements只查询当前员工本人申请，不得自动切换活动草稿。
18. 只有提交工具返回PENDING_APPROVAL或取消工具返回CANCELLED后，才能声称对应动作成功。
19. 工具失败时根据code调整行动，不要把内部异常、密钥或连接信息回复给用户。
20. 回复使用简洁自然的中文，先说明本轮真实完成了什么，再说明还需要用户做什么。

当前意图：{context.intent.value}
当前场景：{context.scene.value}
当前会话状态：{json.dumps(state, ensure_ascii=False)}

{skill_text}
""".strip()

    def _procurement_skills(self) -> str:
        if self._skill_manager is None:
            return ""
        selected_names = {
            "collect-procurement-requirement",
            "confirm-procurement-requirement",
            "recommend-historical-supplier",
        }
        blocks = [
            skill.to_prompt_block()
            for skill in self._skill_manager.skills
            if skill.enabled and skill.name in selected_names
        ]
        if not blocks:
            return ""
        return "采购业务Skills：\n\n" + "\n\n".join(blocks)

    def _result(
        self,
        context: AgentContext,
        response: str,
        trace: AgentTrace,
    ) -> AgentHandleResult:
        state = context.procurement_state
        stage = state.stage if state is not None else AgentStage.COLLECTING_INFORMATION
        return AgentHandleResult(
            response=response,
            scene=context.scene,
            stage=stage,
            intent=context.intent,
            procurement_state=state,
            handled=True,
            trace=trace.export(),
        )

    def _guard_submission_claim(self, context: AgentContext, response: str) -> str:
        if context.intent == IntentCategory.CANCEL_REQUIREMENT:
            if (
                context.procurement_state is not None
                and context.procurement_state.status == "CANCELLED"
            ):
                return response
            if any(phrase in response for phrase in self.FALSE_CANCELLATION_PHRASES):
                return "取消工具没有返回CANCELLED，因此没有执行成功；当前草稿状态未被描述为已取消。"
            required_notice = "本轮没有确认成功取消采购草稿"
            if required_notice not in response:
                return response.rstrip() + f"\n\n{required_notice}。"
            return response
        if context.intent != IntentCategory.CONFIRM_SUBMISSION:
            return response
        if (
            context.procurement_state is not None
            and context.procurement_state.status == "PENDING_APPROVAL"
        ):
            return response
        if any(phrase in response for phrase in self.FALSE_SUBMISSION_PHRASES):
            return "提交工具没有返回PENDING_APPROVAL，因此尚未正式提交审批。"
        required_notice = "本轮没有确认成功提交审批"
        if required_notice not in response:
            return response.rstrip() + f"\n\n{required_notice}。"
        return response
