import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest

from app.modules.agent.chat_schemas import (
    AgentMessageCommand,
    ChatHistoryMessage,
    ChatMessageStatus,
)
from app.modules.agent.chat_service import AgentChatService
from app.modules.agent.chat_store import (
    ConversationBusy,
    InMemoryAgentChatStore,
)
from app.modules.agent.enums import AgentScene, AgentStage
from app.modules.agent.intent_recognizer import IntentCategory
from app.modules.agent.result import AgentHandleResult
from app.shared.errors import DomainError, ErrorCode
from app.shared.identity import CurrentUser


class StubIntentService:
    def __init__(self, intent: IntentCategory = IntentCategory.UNKNOWN) -> None:
        self.intent = intent
        self.histories: list[list[dict[str, str]]] = []

    async def resolve(self, message: str, history: list[dict[str, str]]) -> IntentCategory:
        self.histories.append(history)
        return self.intent


class StubAgentService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.error: Exception | None = None

    async def handle(self, **kwargs) -> AgentHandleResult:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return AgentHandleResult(
            response="你好，我可以帮你整理采购需求。",
            scene=AgentScene.GENERAL_QUERY,
            stage=AgentStage.INTENT_RECOGNITION,
            intent=kwargs["intent"],
        )


class BusyStore(InMemoryAgentChatStore):
    @asynccontextmanager
    async def lock(self, conversation_key: str):
        raise ConversationBusy(conversation_key)
        yield  # pragma: no cover


def command(content: str = "你好") -> AgentMessageCommand:
    return AgentMessageCommand(
        conversation_id="conversation-1",
        client_message_id="client-1",
        content=content,
    )


def actor(code: str = "EMP-1", organization_id: int = 10) -> CurrentUser:
    return CurrentUser(user_code=code, organization_id=organization_id)


@pytest.mark.asyncio
async def test_general_message_is_saved_without_procurement_state() -> None:
    store = InMemoryAgentChatStore()
    agent = StubAgentService()
    intent = StubIntentService()
    service = AgentChatService(agent_service=agent, intent_service=intent, store=store)  # type: ignore[arg-type]

    result = await service.send_message(
        command(), actor=actor(), request_id="request-1", idempotency_key="idem-1"
    )
    messages, total = await service.list_messages(
        "conversation-1", actor=actor(), page=1, page_size=20
    )

    assert result.scene == AgentScene.GENERAL_QUERY
    assert result.active_requirement is None
    assert total == 2
    assert [item.status for item in messages] == [
        ChatMessageStatus.COMPLETED,
        ChatMessageStatus.COMPLETED,
    ]
    assert agent.calls[0]["actor"] == actor()
    assert agent.calls[0]["history"] == []


@pytest.mark.asyncio
async def test_idempotency_replays_same_request_and_rejects_changed_request() -> None:
    store = InMemoryAgentChatStore()
    agent = StubAgentService()
    service = AgentChatService(
        agent_service=agent,  # type: ignore[arg-type]
        intent_service=StubIntentService(),
        store=store,
    )

    first = await service.send_message(
        command(), actor=actor(), request_id="request-1", idempotency_key="same-key"
    )
    replay = await service.send_message(
        command(), actor=actor(), request_id="request-2", idempotency_key="same-key"
    )

    assert replay == first
    assert len(agent.calls) == 1
    with pytest.raises(DomainError) as caught:
        await service.send_message(
            command("另一个问题"),
            actor=actor(),
            request_id="request-3",
            idempotency_key="same-key",
        )
    assert caught.value.code == ErrorCode.IDEMPOTENCY_CONFLICT


@pytest.mark.asyncio
async def test_failed_turn_is_marked_failed_and_not_replayed_to_model() -> None:
    store = InMemoryAgentChatStore()
    agent = StubAgentService()
    intent = StubIntentService()
    service = AgentChatService(agent_service=agent, intent_service=intent, store=store)  # type: ignore[arg-type]
    agent.error = RuntimeError("provider secret must not leak")

    with pytest.raises(DomainError) as caught:
        await service.send_message(
            command(), actor=actor(), request_id="request-1", idempotency_key="failed-key"
        )
    assert caught.value.code == ErrorCode.AGENT_UNAVAILABLE

    agent.error = None
    await service.send_message(
        command("继续"), actor=actor(), request_id="request-2", idempotency_key="next-key"
    )
    messages, _ = await service.list_messages("conversation-1", actor=actor(), page=1, page_size=20)
    assert messages[0].status == ChatMessageStatus.FAILED
    assert intent.histories[-1] == []
    assert agent.calls[-1]["history"] == []


@pytest.mark.asyncio
async def test_conversation_key_isolates_users_and_organizations() -> None:
    store = InMemoryAgentChatStore()
    service = AgentChatService(
        agent_service=StubAgentService(),  # type: ignore[arg-type]
        intent_service=StubIntentService(),
        store=store,
    )
    await service.send_message(
        command(), actor=actor(), request_id="request-1", idempotency_key="idem-1"
    )

    _, other_user_total = await service.list_messages(
        "conversation-1", actor=actor("EMP-2"), page=1, page_size=20
    )
    _, other_org_total = await service.list_messages(
        "conversation-1", actor=actor(organization_id=11), page=1, page_size=20
    )

    assert other_user_total == 0
    assert other_org_total == 0
    assert service.conversation_key(actor(), "conversation-1") == "10:EMP-1:conversation-1"


@pytest.mark.asyncio
async def test_reset_clears_messages_but_does_not_touch_other_user() -> None:
    store = InMemoryAgentChatStore()
    service = AgentChatService(
        agent_service=StubAgentService(),  # type: ignore[arg-type]
        intent_service=StubIntentService(),
        store=store,
    )
    await service.send_message(
        command(), actor=actor(), request_id="request-1", idempotency_key="idem-1"
    )
    await service.send_message(
        command(), actor=actor("EMP-2"), request_id="request-2", idempotency_key="idem-1"
    )

    result = await service.reset_conversation(
        "conversation-1", actor=actor(), idempotency_key="reset-1"
    )
    _, own_total = await service.list_messages(
        "conversation-1", actor=actor(), page=1, page_size=20
    )
    _, other_total = await service.list_messages(
        "conversation-1", actor=actor("EMP-2"), page=1, page_size=20
    )

    assert result.cleared is True
    assert own_total == 0
    assert other_total == 2


@pytest.mark.asyncio
async def test_store_trims_history_to_last_one_hundred_messages() -> None:
    store = InMemoryAgentChatStore(max_messages=100)
    now = datetime.now(UTC)
    for index in range(105):
        await store.append_message(
            "key",
            ChatHistoryMessage(
                message_id=str(index),
                role="USER",
                content=str(index),
                status=ChatMessageStatus.COMPLETED,
                created_at=now,
            ),
        )

    messages = await store.list_messages("key")
    assert len(messages) == 100
    assert messages[0].message_id == "5"


@pytest.mark.asyncio
async def test_busy_conversation_returns_stable_error() -> None:
    service = AgentChatService(
        agent_service=StubAgentService(),  # type: ignore[arg-type]
        intent_service=StubIntentService(),
        store=BusyStore(),
    )

    with pytest.raises(DomainError) as caught:
        await service.send_message(
            command(), actor=actor(), request_id="request-1", idempotency_key="idem-1"
        )
    assert caught.value.code == ErrorCode.CONVERSATION_BUSY


@pytest.mark.asyncio
async def test_conversation_serialization_and_cross_conversation_parallelism() -> None:
    class TrackingAgent(StubAgentService):
        def __init__(self) -> None:
            super().__init__()
            self.active_by_conversation: dict[str, int] = {}
            self.same_conversation_peak = 0
            self.total_peak = 0

        async def handle(self, **kwargs) -> AgentHandleResult:
            conversation_id = str(kwargs["conv_id"])
            self.active_by_conversation[conversation_id] = (
                self.active_by_conversation.get(conversation_id, 0) + 1
            )
            self.same_conversation_peak = max(
                self.same_conversation_peak, self.active_by_conversation[conversation_id]
            )
            self.total_peak = max(self.total_peak, sum(self.active_by_conversation.values()))
            await asyncio.sleep(0.02)
            self.active_by_conversation[conversation_id] -= 1
            return await super().handle(**kwargs)

    agent = TrackingAgent()
    service = AgentChatService(
        agent_service=agent,  # type: ignore[arg-type]
        intent_service=StubIntentService(),
        store=InMemoryAgentChatStore(),
    )
    second_command = command("第二条")
    second_command.client_message_id = "client-2"
    other_command = command("另一个会话")
    other_command.conversation_id = "conversation-2"

    await asyncio.gather(
        service.send_message(command(), actor=actor(), request_id="r1", idempotency_key="i1"),
        service.send_message(second_command, actor=actor(), request_id="r2", idempotency_key="i2"),
        service.send_message(other_command, actor=actor(), request_id="r3", idempotency_key="i3"),
    )

    assert agent.same_conversation_peak == 1
    assert agent.total_peak >= 2
