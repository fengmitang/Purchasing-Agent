import re
from typing import Protocol

from app.modules.agent.context import AgentContext
from app.modules.agent.routes import AgentRoute

PROCUREMENT_TOOL_NAMES = {
    "create_requirement_draft",
    "get_requirement_detail",
    "update_requirement_draft",
    "start_new_requirement",
    "switch_active_requirement",
    "submit_requirement",
    "cancel_requirement",
    "search_historical_suppliers",
    "list_my_requirements",
}

_SUBMIT_CONFIRMATION_PHRASES = (
    "确认提交",
    "确定提交",
    "提交审批",
    "确认无误",
    "信息无误",
)
_CANCEL_CONFIRMATION_PHRASES = ("确认取消", "确认撤销", "确定取消", "确定撤销")
_CANCEL_REASON_PATTERN = re.compile(
    r"(?:因为|由于|原因(?:是|为)?|理由(?:是|为)?)\s*[:：]?\s*(?P<reason>.+)"
)
_CANCEL_FILLER_PATTERN = re.compile(
    r"[，。；、,:：;!！?\s]|采购|需求|申请|草稿|当前|这张|这个|我的|我|请|要|想"
)


class ToolPolicy(Protocol):
    def allowed_tools(self, context: AgentContext) -> set[str]: ...


def has_explicit_submit_confirmation(context: AgentContext) -> bool:
    message = context.message.strip()
    if any(phrase in message for phrase in _SUBMIT_CONFIRMATION_PHRASES):
        return True
    return message in {"确认", "确定", "是的", "可以"} and _history_mentions(
        context, ("提交", "审批")
    )


def has_explicit_cancel_confirmation(context: AgentContext) -> bool:
    message = context.message.strip()
    if any(phrase in message for phrase in _CANCEL_CONFIRMATION_PHRASES):
        return True
    return message in {"确认", "确定", "是的"} and _history_mentions(context, ("取消", "撤销"))


def has_cancel_reason(context: AgentContext) -> bool:
    if _text_has_cancel_reason(context.message):
        return True
    for item in reversed(context.history[-4:]):
        if item.get("role") != "user":
            continue
        content = item.get("content", "")
        if ("取消" in content or "撤销" in content) and _text_has_cancel_reason(content):
            return True
    return False


def _text_has_cancel_reason(message: str) -> bool:
    message = message.strip()
    matched = _CANCEL_REASON_PATTERN.search(message)
    if matched and matched.group("reason").strip(" ，。；、,:：;!！?"):
        return True

    remaining = message
    for phrase in _CANCEL_CONFIRMATION_PHRASES:
        remaining = remaining.replace(phrase, "")
    return len(_CANCEL_FILLER_PATTERN.sub("", remaining)) >= 2


def _history_mentions(context: AgentContext, terms: tuple[str, ...]) -> bool:
    for item in reversed(context.history[-4:]):
        if item.get("role") != "assistant":
            continue
        content = item.get("content", "")
        return any(term in content for term in terms)
    return False


class GeneralToolPolicy:
    def allowed_tools(self, context: AgentContext) -> set[str]:
        return set()


class ProcurementToolPolicy:
    """默认允许采购工具，仅前置限制三类高风险写操作。"""

    def allowed_tools(self, context: AgentContext) -> set[str]:
        if context.route != AgentRoute.PROCUREMENT:
            return set()

        allowed = set(PROCUREMENT_TOOL_NAMES)
        if context.procurement_state is None:
            allowed.remove("update_requirement_draft")
        if not has_explicit_submit_confirmation(context):
            allowed.remove("submit_requirement")
        if not (has_explicit_cancel_confirmation(context) and has_cancel_reason(context)):
            allowed.remove("cancel_requirement")
        return allowed
