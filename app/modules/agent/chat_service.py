import hashlib
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime
from uuid import uuid4

from app.modules.agent.chat_schemas import (
    AgentMessageCommand,
    AgentMessageResult,
    ChatHistoryMessage,
    ChatMessageStatus,
    ChatTurnState,
    ConversationResetResult,
)
from app.modules.agent.chat_store import (
    AgentChatStoreProtocol,
    ChatStoreUnavailable,
    ConversationBusy,
)
from app.modules.agent.intent_service import IntentServiceProtocol
from app.modules.agent.procurement.schemas import RequirementSessionReference
from app.modules.agent.service import AgentService
from app.shared.errors import DomainError, ErrorCode
from app.shared.identity import CurrentUser

logger = logging.getLogger(__name__)


class AgentChatService:
    def __init__(
        self,
        *,
        agent_service: AgentService,
        intent_service: IntentServiceProtocol,
        store: AgentChatStoreProtocol,
        history_replay_limit: int = 12,
    ) -> None:
        self._agent = agent_service
        self._intent = intent_service
        self._store = store
        self._history_replay_limit = history_replay_limit

    async def send_message(
        self,
        command: AgentMessageCommand,
        *,
        actor: CurrentUser,
        request_id: str,
        idempotency_key: str,
    ) -> AgentMessageResult:
        conversation_key = self.conversation_key(actor, command.conversation_id)
        request_hash = self._request_hash(command.model_dump(mode="json"))
        turn_state = ChatTurnState.RECEIVED
        user_message_id = uuid4().hex
        user_message_recorded = False
        try:
            async with self._store.lock(conversation_key):
                replay = await self._store.get_idempotency(conversation_key, idempotency_key)
                if replay is not None:
                    saved_hash, response = replay
                    if saved_hash != request_hash:
                        raise DomainError(
                            ErrorCode.IDEMPOTENCY_CONFLICT,
                            "同一幂等键不能用于不同的聊天请求",
                        )
                    return AgentMessageResult.model_validate(response)

                history = await self._store.list_messages(conversation_key)
                state = await self._store.get_state(conversation_key)
                turn_state = ChatTurnState.SESSION_LOADED
                now = datetime.now(UTC)
                await self._store.append_message(
                    conversation_key,
                    ChatHistoryMessage(
                        message_id=user_message_id,
                        client_message_id=command.client_message_id,
                        role="USER",
                        content=command.content,
                        status=ChatMessageStatus.PROCESSING,
                        created_at=now,
                    ),
                )
                user_message_recorded = True
                replay_history = self._replay_history(history)
                intent = await self._intent.resolve(command.content, replay_history)
                turn_state = ChatTurnState.INTENT_RESOLVED
                turn_state = ChatTurnState.AGENT_RUNNING
                result = await self._agent.handle(
                    intent=intent,
                    message=command.content,
                    user_id=actor.user_code,
                    conv_id=command.conversation_id,
                    request_id=request_id,
                    actor=actor,
                    history=replay_history,
                    state_override=state,
                    persist_state=False,
                )
                created_at = datetime.now(UTC)
                response = AgentMessageResult(
                    message_id=uuid4().hex,
                    conversation_id=command.conversation_id,
                    content=result.response,
                    intent=result.intent,
                    scene=result.scene,
                    stage=result.stage,
                    active_requirement=(
                        RequirementSessionReference(
                            requirement_id=result.procurement_state.requirement_id,
                            requirement_no=result.procurement_state.requirement_no,
                            status=result.procurement_state.status,
                        )
                        if result.procurement_state is not None
                        else None
                    ),
                    created_at=created_at,
                )
                await self._store.append_message(
                    conversation_key,
                    ChatHistoryMessage(
                        message_id=response.message_id,
                        role="ASSISTANT",
                        content=response.content,
                        status=ChatMessageStatus.COMPLETED,
                        created_at=created_at,
                    ),
                )
                if result.procurement_state is not None:
                    await self._store.save_state(conversation_key, result.procurement_state)
                await self._store.set_message_status(
                    conversation_key, user_message_id, ChatMessageStatus.COMPLETED
                )
                turn_state = ChatTurnState.SAVED
                await self._store.save_idempotency(
                    conversation_key,
                    idempotency_key,
                    request_hash,
                    response.model_dump(mode="json"),
                )
                turn_state = ChatTurnState.RESPONDED
                return response
        except DomainError:
            if user_message_recorded:
                with suppress(Exception):
                    await self._store.set_message_status(
                        conversation_key, user_message_id, ChatMessageStatus.FAILED
                    )
            raise
        except ConversationBusy as exc:
            raise DomainError(
                ErrorCode.CONVERSATION_BUSY,
                "当前会话正在处理另一条消息，请稍后重试",
            ) from exc
        except ChatStoreUnavailable as exc:
            if user_message_recorded:
                with suppress(Exception):
                    await self._store.set_message_status(
                        conversation_key, user_message_id, ChatMessageStatus.FAILED
                    )
            raise DomainError(
                ErrorCode.AGENT_UNAVAILABLE,
                "聊天会话服务暂时不可用，请稍后重试",
            ) from exc
        except Exception as exc:
            turn_state = ChatTurnState.FAILED
            with suppress(Exception):
                await self._store.set_message_status(
                    conversation_key, user_message_id, ChatMessageStatus.FAILED
                )
            logger.warning(
                "Agent chat turn failed request_id=%s state=%s",
                request_id,
                turn_state.value,
                exc_info=True,
            )
            raise DomainError(
                ErrorCode.AGENT_UNAVAILABLE,
                "Agent 服务暂时不可用，请稍后重试",
            ) from exc

    async def list_messages(
        self,
        conversation_id: str,
        *,
        actor: CurrentUser,
        page: int,
        page_size: int,
    ) -> tuple[list[ChatHistoryMessage], int]:
        key = self.conversation_key(actor, conversation_id)
        try:
            messages = await self._store.list_messages(key)
        except ChatStoreUnavailable as exc:
            raise DomainError(ErrorCode.AGENT_UNAVAILABLE, "聊天会话服务暂时不可用") from exc
        total = len(messages)
        start = (page - 1) * page_size
        return messages[start : start + page_size], total

    async def reset_conversation(
        self,
        conversation_id: str,
        *,
        actor: CurrentUser,
        idempotency_key: str,
    ) -> ConversationResetResult:
        key = self.conversation_key(actor, conversation_id)
        request_hash = self._request_hash(
            {"operation": "reset", "conversation_id": conversation_id}
        )
        try:
            async with self._store.lock(key):
                replay = await self._store.get_idempotency(key, idempotency_key)
                if replay is not None:
                    saved_hash, response = replay
                    if saved_hash != request_hash:
                        raise DomainError(
                            ErrorCode.IDEMPOTENCY_CONFLICT,
                            "同一幂等键不能用于不同的聊天请求",
                        )
                    return ConversationResetResult.model_validate(response)
                await self._store.clear(key)
                result = ConversationResetResult(conversation_id=conversation_id)
                await self._store.save_idempotency(
                    key, idempotency_key, request_hash, result.model_dump(mode="json")
                )
                return result
        except DomainError:
            raise
        except ConversationBusy as exc:
            raise DomainError(ErrorCode.CONVERSATION_BUSY, "当前会话正在处理消息") from exc
        except ChatStoreUnavailable as exc:
            raise DomainError(ErrorCode.AGENT_UNAVAILABLE, "聊天会话服务暂时不可用") from exc

    @staticmethod
    def conversation_key(actor: CurrentUser, conversation_id: str) -> str:
        safe_user = actor.user_code.replace(":", "_")[:128]
        return f"{actor.organization_id}:{safe_user}:{conversation_id}"

    def _replay_history(self, messages: list[ChatHistoryMessage]) -> list[dict[str, str]]:
        completed = [
            {
                "role": "user" if message.role == "USER" else "assistant",
                "content": message.content,
            }
            for message in messages
            if message.status == ChatMessageStatus.COMPLETED
        ]
        return completed[-self._history_replay_limit :]

    @staticmethod
    def _request_hash(payload: dict[str, object]) -> str:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
