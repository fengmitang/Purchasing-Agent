from dataclasses import dataclass, field

from app.modules.agent.enums import AgentScene, AgentStage, IntentCategory
from app.modules.agent.memory import KnowledgeItem, MemoryItem
from app.modules.agent.procurement.schemas import ProcurementSessionState
from app.modules.agent.routes import AgentRoute
from app.shared.identity import CurrentUser


@dataclass
class AgentContext:
    """单次请求上下文。身份凭证和对话内容不会写入Redis。"""

    request_id: str
    user_id: str
    conv_id: str
    message: str
    actor: CurrentUser
    history: list[dict[str, str]] = field(default_factory=list)
    intent: IntentCategory = IntentCategory.UNKNOWN
    scene: AgentScene = AgentScene.GENERAL_QUERY
    stage: AgentStage = AgentStage.INTENT_RECOGNITION
    procurement_state: ProcurementSessionState | None = None
    memory_items: list[MemoryItem] = field(default_factory=list)
    knowledge_items: list[KnowledgeItem] = field(default_factory=list)
    route: AgentRoute | None = None
    route_needs_clarification: bool = False
