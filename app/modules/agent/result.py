from dataclasses import dataclass, field
from typing import Any

from app.modules.agent.enums import AgentScene, AgentStage
from app.modules.agent.intent_recognizer import IntentCategory
from app.modules.agent.procurement.schemas import ProcurementSessionState


@dataclass
class AgentHandleResult:
    response: str
    scene: AgentScene
    stage: AgentStage
    intent: IntentCategory
    procurement_state: ProcurementSessionState | None = None
    handled: bool = True
    trace: list[dict[str, Any]] = field(default_factory=list)
