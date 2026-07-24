from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.modules.agent.enums import IntentCategory


class AgentRoute(StrEnum):
    GENERAL = "general"
    PROCUREMENT = "procurement"


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: AgentRoute
    confidence: float = Field(ge=0, le=1)
    explicit_switch: bool = False
    needs_clarification: bool = False
    effective_intent: IntentCategory | None = None


class RouteResolver:
    """Resolve domain routing without deciding a procurement operation."""

    def resolve(
        self,
        *,
        message: str = "",
        intent: object | None = None,
        has_procurement_state: bool,
        active_route: AgentRoute | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> RouteDecision:
        text = message.strip().lower()
        switch_to_general = any(token in text for token in ("切换到通用", "退出采购", "general"))
        switch_to_procurement = any(
            token in text for token in ("切换到采购", "进入采购", "procurement")
        )
        if switch_to_general and not switch_to_procurement:
            return RouteDecision(route=AgentRoute.GENERAL, confidence=1.0, explicit_switch=True)
        if switch_to_procurement:
            return RouteDecision(route=AgentRoute.PROCUREMENT, confidence=1.0, explicit_switch=True)
        last_assistant = next(
            (
                str(item.get("content", ""))
                for item in reversed(history or [])
                if item.get("role") == "assistant"
            ),
            "",
        )
        confirms_procurement = text in {"是", "是的", "好的", "对", "确认", "进入"}
        if (
            active_route == AgentRoute.GENERAL
            and confirms_procurement
            and "是否要进入采购流程" in last_assistant
        ):
            return RouteDecision(route=AgentRoute.PROCUREMENT, confidence=1.0, explicit_switch=True)
        if active_route is not None:
            return RouteDecision(route=active_route, confidence=1.0)
        if has_procurement_state:
            return RouteDecision(route=AgentRoute.PROCUREMENT, confidence=1.0)

        route_text = " ".join(
            [
                *(str(item.get("content", "")) for item in (history or [])[-6:]),
                text,
            ]
        )
        procurement_markers = (
            "采购",
            "购买",
            "买",
            "申请买",
            "需求草稿",
            "供应商",
            "提交审批",
            "采购状态",
            "采购进度",
        )
        if any(marker in route_text for marker in procurement_markers):
            return RouteDecision(route=AgentRoute.PROCUREMENT, confidence=0.95)
        general_markers = ("你好", "您好", "谢谢", "你是谁", "帮助")
        if any(marker in text for marker in general_markers):
            return RouteDecision(route=AgentRoute.GENERAL, confidence=0.95)

        value = getattr(intent, "value", str(intent)) if intent is not None else "unknown"
        if value not in {"unknown", "general_query", "none"}:
            return RouteDecision(
                route=AgentRoute.PROCUREMENT,
                confidence=0.9,
                effective_intent=(intent if isinstance(intent, IntentCategory) else None),
            )
        return RouteDecision(
            route=AgentRoute.GENERAL,
            confidence=0.0,
            needs_clarification=True,
            effective_intent=(intent if isinstance(intent, IntentCategory) else None),
        )

    def effective_intent(
        self,
        intent: IntentCategory,
        *,
        has_procurement_state: bool,
        history: list[dict[str, str]] | None = None,
    ) -> IntentCategory:
        if intent == IntentCategory.UNKNOWN and has_procurement_state:
            return IntentCategory.SUPPLEMENT_REQUIREMENT
        if intent == IntentCategory.UNKNOWN and self._history_has_procurement_context(
            history or []
        ):
            return IntentCategory.CREATE_REQUIREMENT
        return intent

    @staticmethod
    def _history_has_procurement_context(history: list[dict[str, str]]) -> bool:
        markers = ("采购草稿", "采购需求", "确认提交", "补充采购", "procurement")
        return any(
            any(marker in str(item.get("content", "")) for marker in markers)
            for item in history[-6:]
        )
