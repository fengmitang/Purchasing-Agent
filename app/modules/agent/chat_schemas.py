from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.agent.enums import AgentScene, AgentStage
from app.modules.agent.intent_recognizer import IntentCategory
from app.modules.agent.procurement.schemas import RequirementSessionReference

SafeIdentifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9._-]{1,100}$"),
]


class ChatMessageStatus(StrEnum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ChatTurnState(StrEnum):
    RECEIVED = "RECEIVED"
    SESSION_LOADED = "SESSION_LOADED"
    INTENT_RESOLVED = "INTENT_RESOLVED"
    AGENT_RUNNING = "AGENT_RUNNING"
    SAVED = "SAVED"
    RESPONDED = "RESPONDED"
    FAILED = "FAILED"


class AgentMessageCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    conversation_id: SafeIdentifier
    client_message_id: SafeIdentifier
    content: str = Field(min_length=1, max_length=10_000)


class ChatHistoryMessage(BaseModel):
    message_id: str
    client_message_id: str | None = None
    role: Literal["USER", "ASSISTANT"]
    content: str
    status: ChatMessageStatus
    created_at: datetime


class AgentMessageResult(BaseModel):
    message_id: str
    conversation_id: str
    role: Literal["ASSISTANT"] = "ASSISTANT"
    content: str
    intent: IntentCategory
    scene: AgentScene
    stage: AgentStage
    active_requirement: RequirementSessionReference | None = None
    created_at: datetime


class ConversationResetResult(BaseModel):
    conversation_id: str
    cleared: bool = True
