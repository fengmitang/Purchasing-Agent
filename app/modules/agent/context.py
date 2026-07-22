from dataclasses import dataclass, field

from app.modules.agent.enums import AgentScene, AgentStage
from app.modules.agent.intent_recognizer import IntentCategory
from app.modules.agent.procurement.schemas import ProcurementSessionState
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
