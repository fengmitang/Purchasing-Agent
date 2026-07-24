from typing import Any

from app.modules.agent.model import AgentModelProtocol
from app.modules.agent.procurement.protocols import RequirementBackendProtocol
from app.modules.agent.procurement.session_store import ProcurementSessionStoreProtocol
from app.modules.agent.runner import ProcurementAgentRunner
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
    runner = ProcurementAgentRunner(
        model=model,
        registry=registry,
        executor=ToolExecutor(registry),
        skill_manager=skill_manager,
        max_iterations=max_iterations,
    )
    return AgentService(runner=runner, session_store=session_store)
