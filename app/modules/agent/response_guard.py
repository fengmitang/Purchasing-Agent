from app.modules.agent.context import AgentContext
from app.modules.agent.enums import IntentCategory


class ResponseGuard:
    """Prevents model-only claims of successful high-risk actions."""

    def guard(self, context: AgentContext, response: str) -> str:
        state = context.procurement_state
        if context.intent == IntentCategory.CANCEL_REQUIREMENT:
            if state is not None and state.status == "CANCELLED":
                return response
            if any(token in response for token in ("取消成功", "已经取消", "已取消", "撤销成功")):
                return "取消工具没有返回 CANCELLED，因此本次取消没有执行成功。"
            return response
        if context.intent == IntentCategory.CONFIRM_SUBMISSION:
            if state is not None and state.status == "PENDING_APPROVAL":
                return response
            if any(
                token in response
                for token in ("提交成功", "成功提交", "已经提交", "已提交审批", "提交完成")
            ):
                return "提交工具没有返回 PENDING_APPROVAL，因此尚未正式提交。"
        return response
