from dataclasses import dataclass
from typing import Protocol

from app.modules.agent.context import AgentContext
from app.modules.agent.policies import GeneralToolPolicy, ToolPolicy
from app.modules.agent.routes import AgentRoute


class PromptProvider(Protocol):
    def build(self, context: AgentContext) -> str: ...


class SkillSelector(Protocol):
    def select(self, context: AgentContext) -> str: ...


class SkillManagerSelector:
    def __init__(self, manager: object, allowed_names: set[str]) -> None:
        self._manager = manager
        self._allowed_names = allowed_names

    def select(self, context: AgentContext) -> str:
        skills = getattr(self._manager, "skills", [])
        blocks = [
            skill.to_prompt_block()
            for skill in skills
            if skill.enabled and skill.name in self._allowed_names
        ]
        return "\n\n".join(blocks)


@dataclass(frozen=True)
class AgentDefinition:
    route: AgentRoute
    prompt_provider: PromptProvider
    tool_policy: ToolPolicy
    skill_selector: SkillSelector | None = None


class GeneralPromptProvider:
    def build(self, context: AgentContext) -> str:
        if context.route_needs_clarification:
            return (
                "你是数据中心采购系统的通用助手。当前无法确定用户是在进行普通对话，"
                "还是希望办理采购。请用一句简洁中文安全追问用户是否要进入采购流程。"
                "当前没有任何业务工具，不得声称查询或修改了采购数据。"
            )
        return (
            "你是数据中心采购系统的通用助手。只能进行通用对话，当前场景没有业务工具。"
            "未知事实要明确说明，不得声称查询了内部数据或修改了采购状态。"
        )


def build_general_agent_definition() -> AgentDefinition:
    return AgentDefinition(
        route=AgentRoute.GENERAL,
        prompt_provider=GeneralPromptProvider(),
        tool_policy=GeneralToolPolicy(),
    )
