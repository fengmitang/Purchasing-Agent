from app.modules.agent.context import AgentContext
from app.modules.agent.enums import AgentScene, AgentStage, IntentCategory
from app.modules.agent.memory import KnowledgeItem, MemoryItem
from app.modules.agent.policies import (
    PROCUREMENT_TOOL_NAMES,
    GeneralToolPolicy,
    ProcurementToolPolicy,
)
from app.modules.agent.routes import AgentRoute, RouteResolver
from app.modules.agent.runner import AgentLoopRuntime


def test_route_resolver_keeps_procurement_context_in_procurement() -> None:
    decision = RouteResolver().resolve(
        intent=IntentCategory.UNKNOWN,
        has_procurement_state=True,
    )
    assert decision.route == AgentRoute.PROCUREMENT


def test_route_resolver_honors_explicit_switch_to_general() -> None:
    decision = RouteResolver().resolve(
        message="退出采购，先聊点别的",
        intent=IntentCategory.UNKNOWN,
        has_procurement_state=True,
        active_route=AgentRoute.PROCUREMENT,
    )
    assert decision.route == AgentRoute.GENERAL
    assert decision.explicit_switch is True


def test_route_resolver_honors_explicit_switch_to_procurement() -> None:
    decision = RouteResolver().resolve(
        message="切换到采购",
        intent=IntentCategory.UNKNOWN,
        has_procurement_state=False,
        active_route=AgentRoute.GENERAL,
    )
    assert decision.route == AgentRoute.PROCUREMENT
    assert decision.explicit_switch is True


def test_route_resolver_marks_unknown_new_session_for_safe_clarification() -> None:
    decision = RouteResolver().resolve(
        message="帮我处理一下",
        has_procurement_state=False,
    )
    assert decision.route == AgentRoute.GENERAL
    assert decision.needs_clarification is True
    assert decision.confidence == 0


def test_route_resolver_keeps_active_general_without_explicit_switch() -> None:
    decision = RouteResolver().resolve(
        message="我想采购服务器",
        has_procurement_state=False,
        active_route=AgentRoute.GENERAL,
    )
    assert decision.route == AgentRoute.GENERAL
    assert decision.explicit_switch is False


def test_route_resolver_treats_affirmative_clarification_as_explicit_switch() -> None:
    decision = RouteResolver().resolve(
        message="是的",
        has_procurement_state=False,
        active_route=AgentRoute.GENERAL,
        history=[{"role": "assistant", "content": "请确认是否要进入采购流程。"}],
    )
    assert decision.route == AgentRoute.PROCUREMENT
    assert decision.explicit_switch is True


def test_general_policy_never_exposes_tools() -> None:
    context = AgentContext("r", "u", "c", "hello", actor=None)  # type: ignore[arg-type]
    assert GeneralToolPolicy().allowed_tools(context) == set()


def test_procurement_policy_only_blocks_three_guarded_writes_without_draft() -> None:
    context = AgentContext(
        "r",
        "u",
        "c",
        "buy servers",
        actor=None,  # type: ignore[arg-type]
        intent=IntentCategory.CREATE_REQUIREMENT,
        scene=AgentScene.PROCUREMENT_REQUIREMENT,
        stage=AgentStage.COLLECTING_INFORMATION,
        route=AgentRoute.PROCUREMENT,
    )
    assert ProcurementToolPolicy().allowed_tools(context) == PROCUREMENT_TOOL_NAMES - {
        "update_requirement_draft",
        "submit_requirement",
        "cancel_requirement",
    }


def test_procurement_policy_does_not_narrow_tools_by_intent() -> None:
    context = AgentContext(
        "r",
        "u",
        "c",
        "搜索科士达功率模块历史采购和供应商白名单",
        actor=None,  # type: ignore[arg-type]
        intent=IntentCategory.SEARCH_HISTORICAL_SUPPLIERS,
        scene=AgentScene.PROCUREMENT_REQUIREMENT,
        stage=AgentStage.COLLECTING_INFORMATION,
        route=AgentRoute.PROCUREMENT,
        procurement_state=object(),  # type: ignore[arg-type]
    )
    assert ProcurementToolPolicy().allowed_tools(context) == PROCUREMENT_TOOL_NAMES - {
        "submit_requirement",
        "cancel_requirement",
    }


def test_procurement_policy_allows_submit_only_after_explicit_confirmation() -> None:
    context = AgentContext(
        "r",
        "u",
        "c",
        "信息无误，确认提交审批",
        actor=None,  # type: ignore[arg-type]
        route=AgentRoute.PROCUREMENT,
        procurement_state=object(),  # type: ignore[arg-type]
    )
    allowed = ProcurementToolPolicy().allowed_tools(context)
    assert "submit_requirement" in allowed
    assert "cancel_requirement" not in allowed
    assert "update_requirement_draft" in allowed


def test_procurement_policy_requires_cancel_confirmation_and_reason() -> None:
    context = AgentContext(
        "r",
        "u",
        "c",
        "确认取消采购",
        actor=None,  # type: ignore[arg-type]
        route=AgentRoute.PROCUREMENT,
        procurement_state=object(),  # type: ignore[arg-type]
    )
    assert "cancel_requirement" not in ProcurementToolPolicy().allowed_tools(context)

    context.message = "需求不再存在，确认取消"
    assert "cancel_requirement" in ProcurementToolPolicy().allowed_tools(context)


def test_procurement_policy_accepts_contextual_submit_confirmation() -> None:
    context = AgentContext(
        "r",
        "u",
        "c",
        "确认",
        actor=None,  # type: ignore[arg-type]
        route=AgentRoute.PROCUREMENT,
        procurement_state=object(),  # type: ignore[arg-type]
        history=[{"role": "assistant", "content": "信息完整，是否提交审批？"}],
    )
    assert "submit_requirement" in ProcurementToolPolicy().allowed_tools(context)


def test_procurement_policy_accepts_prior_cancel_reason_on_confirmation_turn() -> None:
    context = AgentContext(
        "r",
        "u",
        "c",
        "确认",
        actor=None,  # type: ignore[arg-type]
        route=AgentRoute.PROCUREMENT,
        procurement_state=object(),  # type: ignore[arg-type]
        history=[
            {"role": "user", "content": "需求不再存在，我想取消"},
            {"role": "assistant", "content": "请确认是否取消这张采购草稿。"},
        ],
    )
    assert "cancel_requirement" in ProcurementToolPolicy().allowed_tools(context)


def test_reference_prompt_is_context_only() -> None:
    context = AgentContext(
        "r",
        "u",
        "c",
        "buy",
        actor=None,  # type: ignore[arg-type]
        memory_items=[MemoryItem("remembered")],
        knowledge_items=[KnowledgeItem("documented")],
    )
    prompt = AgentLoopRuntime._reference_prompt(context)
    assert "仅作为参考" in prompt
    assert "remembered" in prompt
    assert "documented" in prompt
