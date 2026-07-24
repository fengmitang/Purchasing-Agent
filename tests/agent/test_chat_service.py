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
    ChatStoreUnavailable,
    ConversationBusy,
    InMemoryAgentChatStore,
)
from app.modules.agent.enums import AgentScene, AgentStage, IntentCategory
from app.modules.agent.procurement.schemas import ProcurementSessionState
from app.modules.agent.result import AgentHandleResult
from app.modules.agent.routes import AgentRoute
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

    async def get_session_state(self, organization_id: int, user_id: str, conv_id: str) -> None:
        return None

    async def save_session_state(self, organization_id, user_id, conv_id, state) -> None:
        self.calls.append(
            {
                "operation": "save_session_state",
                "organization_id": organization_id,
                "user_id": user_id,
                "conv_id": conv_id,
            }
        )

    async def clear_session_state(self, organization_id: int, user_id: str, conv_id: str) -> None:
        self.calls.append(
            {
                "operation": "clear_session_state",
                "organization_id": organization_id,
                "user_id": user_id,
                "conv_id": conv_id,
            }
        )


class BusyStore(InMemoryAgentChatStore):
    @asynccontextmanager
    async def lock(self, conversation_key: str):
        raise ConversationBusy(conversation_key)
        yield  # pragma: no cover


class FailingIdempotencyStore(InMemoryAgentChatStore):
    async def save_idempotency(self, *args, **kwargs) -> None:
        raise ChatStoreUnavailable("redis unavailable")


class FailOnceClearStore(InMemoryAgentChatStore):
    def __init__(self) -> None:
        super().__init__()
        self.clear_calls = 0

    async def clear(self, conversation_key: str) -> None:
        self.clear_calls += 1
        if self.clear_calls == 1:
            raise ChatStoreUnavailable("redis unavailable")
        await super().clear(conversation_key)


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
    service = AgentChatService(
        agent_service=agent,
        procurement_intent_resolver=intent,
        store=store,
    )  # type: ignore[arg-type]

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
        procurement_intent_resolver=StubIntentService(),
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
    service = AgentChatService(
        agent_service=agent,
        procurement_intent_resolver=intent,
        store=store,
    )  # type: ignore[arg-type]
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
    assert intent.histories == []
    assert agent.calls[-1]["history"] == []


@pytest.mark.asyncio
async def test_conversation_key_isolates_users_and_organizations() -> None:
    store = InMemoryAgentChatStore()
    service = AgentChatService(
        agent_service=StubAgentService(),  # type: ignore[arg-type]
        procurement_intent_resolver=StubIntentService(),
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
    agent = StubAgentService()
    service = AgentChatService(
        agent_service=agent,  # type: ignore[arg-type]
        procurement_intent_resolver=StubIntentService(),
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
    assert agent.calls[-1] == {
        "operation": "clear_session_state",
        "organization_id": 10,
        "user_id": "EMP-1",
        "conv_id": "conversation-1",
    }


@pytest.mark.asyncio
async def test_general_route_does_not_call_procurement_intent_resolver() -> None:
    store = InMemoryAgentChatStore()
    intent = StubIntentService(IntentCategory.CREATE_REQUIREMENT)
    agent = StubAgentService()
    service = AgentChatService(
        agent_service=agent,  # type: ignore[arg-type]
        procurement_intent_resolver=intent,
        store=store,
    )

    await service.send_message(
        command("你好"), actor=actor(), request_id="request-general", idempotency_key="general"
    )

    assert intent.histories == []
    assert agent.calls[0]["intent"] == IntentCategory.UNKNOWN
    assert agent.calls[0]["route_decision"].route == AgentRoute.GENERAL


@pytest.mark.asyncio
async def test_procurement_route_resolves_procurement_intent_after_domain_route() -> None:
    store = InMemoryAgentChatStore()
    intent = StubIntentService(IntentCategory.CREATE_REQUIREMENT)
    agent = StubAgentService()
    service = AgentChatService(
        agent_service=agent,  # type: ignore[arg-type]
        procurement_intent_resolver=intent,
        store=store,
    )

    await service.send_message(
        command("我要采购两台服务器"),
        actor=actor(),
        request_id="request-procurement",
        idempotency_key="procurement",
    )

    assert intent.histories == [[]]
    assert agent.calls[0]["intent"] == IntentCategory.CREATE_REQUIREMENT
    assert agent.calls[0]["route_decision"].route == AgentRoute.PROCUREMENT


@pytest.mark.asyncio
async def test_reset_session_store_failure_returns_safe_error() -> None:
    class FailingResetAgent(StubAgentService):
        async def clear_session_state(
            self, organization_id: int, user_id: str, conv_id: str
        ) -> None:
            raise RuntimeError("redis connection secret")

    service = AgentChatService(
        agent_service=FailingResetAgent(),  # type: ignore[arg-type]
        procurement_intent_resolver=StubIntentService(),
        store=InMemoryAgentChatStore(),
    )

    with pytest.raises(DomainError) as caught:
        await service.reset_conversation(
            "conversation-1",
            actor=actor(),
            idempotency_key="reset-failure",
        )

    assert caught.value.code == ErrorCode.AGENT_UNAVAILABLE
    assert "secret" not in caught.value.message


@pytest.mark.asyncio
async def test_failed_commit_rolls_back_session_route_and_both_messages() -> None:
    previous = ProcurementSessionState(
        requirement_id=1,
        requirement_no="PR-1",
        version=1,
        status="DRAFT",
    )
    updated = ProcurementSessionState(
        requirement_id=2,
        requirement_no="PR-2",
        version=1,
        status="DRAFT",
    )

    class StatefulAgent(StubAgentService):
        def __init__(self) -> None:
            super().__init__()
            self.state = previous

        async def get_session_state(self, *args) -> ProcurementSessionState:
            return self.state.model_copy(deep=True)

        async def handle(self, **kwargs) -> AgentHandleResult:
            return AgentHandleResult(
                response="已创建新草稿",
                scene=AgentScene.PROCUREMENT_REQUIREMENT,
                stage=AgentStage.COLLECTING_INFORMATION,
                intent=IntentCategory.CREATE_REQUIREMENT,
                procurement_state=updated,
            )

        async def save_session_state(self, *args) -> None:
            self.state = args[-1].model_copy(deep=True)

    store = FailingIdempotencyStore()
    agent = StatefulAgent()
    key = AgentChatService.conversation_key(actor(), "conversation-1")
    await store.save_route(key, AgentRoute.GENERAL)
    service = AgentChatService(
        agent_service=agent,  # type: ignore[arg-type]
        procurement_intent_resolver=StubIntentService(IntentCategory.CREATE_REQUIREMENT),
        store=store,
    )

    with pytest.raises(DomainError):
        await service.send_message(
            command("切换到采购"),
            actor=actor(),
            request_id="failed-commit",
            idempotency_key="failed-commit",
        )

    messages = await store.list_messages(key)
    assert [message.status for message in messages] == [
        ChatMessageStatus.FAILED,
        ChatMessageStatus.FAILED,
    ]
    assert agent.state.requirement_id == previous.requirement_id
    assert await store.get_route(key) == AgentRoute.GENERAL
    assert service._replay_history(messages) == []


@pytest.mark.asyncio
async def test_reset_retries_to_convergence_after_chat_store_failure() -> None:
    store = FailOnceClearStore()
    agent = StubAgentService()
    service = AgentChatService(
        agent_service=agent,  # type: ignore[arg-type]
        procurement_intent_resolver=StubIntentService(),
        store=store,
    )
    await service.send_message(
        command(),
        actor=actor(),
        request_id="before-reset",
        idempotency_key="before-reset",
    )

    with pytest.raises(DomainError) as first:
        await service.reset_conversation(
            "conversation-1",
            actor=actor(),
            idempotency_key="retryable-reset",
        )
    assert first.value.code == ErrorCode.AGENT_UNAVAILABLE

    result = await service.reset_conversation(
        "conversation-1",
        actor=actor(),
        idempotency_key="retryable-reset",
    )
    messages, total = await service.list_messages(
        "conversation-1",
        actor=actor(),
        page=1,
        page_size=20,
    )

    assert result.cleared is True
    assert total == 0
    assert messages == []
    assert store.clear_calls == 2
    clear_calls = [call for call in agent.calls if call.get("operation") == "clear_session_state"]
    assert len(clear_calls) == 2


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
        procurement_intent_resolver=StubIntentService(),
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
        procurement_intent_resolver=StubIntentService(),
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
