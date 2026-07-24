from typing import Any

from app.modules.agent.definitions import (
    AgentDefinition,
    SkillManagerSelector,
    build_general_agent_definition,
)
from app.modules.agent.model import AgentModelProtocol
from app.modules.agent.policies import ProcurementToolPolicy
from app.modules.agent.procurement.prompt import ProcurementPromptProvider
from app.modules.agent.procurement.protocols import RequirementBackendProtocol
from app.modules.agent.procurement.session_store import ProcurementSessionStoreProtocol
from app.modules.agent.routes import AgentRoute
from app.modules.agent.runner import AgentLoopRuntime
from app.modules.agent.service import AgentService
from app.modules.agent.tools.executor import ToolExecutor
from app.modules.agent.tools.registry import ToolRegistry
from app.modules.agent.tools.requirement_tools import (
    CancelRequirementTool,
    CreateRequirementDraftTool,
    GetRequirementDetailTool,
    ListMyRequirementsTool,
    SearchHistoricalSuppliersTool,
    StartNewRequirementTool,
    SubmitRequirementTool,
    SwitchActiveRequirementTool,
    UpdateRequirementDraftTool,
)


def build_procurement_agent_service(
    backend: RequirementBackendProtocol,
    model: AgentModelProtocol,
    session_store: ProcurementSessionStoreProtocol,
    *,
    skill_manager: Any | None = None,
    max_iterations: int = 6,
) -> AgentService:
    registry = ToolRegistry()
    registry.register(CreateRequirementDraftTool(backend))
    registry.register(StartNewRequirementTool(backend))
    registry.register(GetRequirementDetailTool(backend))
    registry.register(UpdateRequirementDraftTool(backend))
    registry.register(SwitchActiveRequirementTool(backend))
    registry.register(SubmitRequirementTool(backend))
    registry.register(CancelRequirementTool(backend))
    registry.register(SearchHistoricalSuppliersTool(backend))
    registry.register(ListMyRequirementsTool(backend))
    skill_selector = (
        SkillManagerSelector(
            skill_manager,
            {
                "collect-procurement-requirement",
                "confirm-procurement-requirement",
                "recommend-historical-supplier",
            },
        )
        if skill_manager is not None
        else None
    )
    definition = AgentDefinition(
        route=AgentRoute.PROCUREMENT,
        prompt_provider=ProcurementPromptProvider(skill_selector),
        tool_policy=ProcurementToolPolicy(),
        skill_selector=skill_selector,
    )
    runner = AgentLoopRuntime(
        model=model,
        registry=registry,
        executor=ToolExecutor(registry),
        max_iterations=max_iterations,
        definitions={
            AgentRoute.GENERAL: build_general_agent_definition(),
            AgentRoute.PROCUREMENT: definition,
        },
    )
    return AgentService(runner=runner, session_store=session_store)
