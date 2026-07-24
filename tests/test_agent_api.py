from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.dependencies import get_agent_chat_service
from app.bootstrap import create_application
from app.modules.agent.chat_schemas import (
    AgentMessageResult,
    ChatHistoryMessage,
    ChatMessageStatus,
    ConversationResetResult,
)
from app.modules.agent.enums import AgentScene, AgentStage, IntentCategory


class StubChatService:
    def __init__(self) -> None:
        self.calls = []

    async def send_message(self, command, **kwargs):
        self.calls.append(("send", command, kwargs))
        return AgentMessageResult(
            message_id="assistant-1",
            conversation_id=command.conversation_id,
            content="请告诉我需要采购什么。",
            intent=IntentCategory.UNKNOWN,
            scene=AgentScene.GENERAL_QUERY,
            stage=AgentStage.INTENT_RECOGNITION,
            created_at=datetime(2026, 7, 21, tzinfo=UTC),
        )

    async def list_messages(self, conversation_id, **kwargs):
        self.calls.append(("list", conversation_id, kwargs))
        return (
            [
                ChatHistoryMessage(
                    message_id="user-1",
                    role="USER",
                    content="你好",
                    status=ChatMessageStatus.COMPLETED,
                    created_at=datetime(2026, 7, 21, tzinfo=UTC),
                )
            ],
            1,
        )

    async def reset_conversation(self, conversation_id, **kwargs):
        self.calls.append(("reset", conversation_id, kwargs))
        return ConversationResetResult(conversation_id=conversation_id)


def build_client(service: StubChatService | None = None):
    application = create_application()
    if service is not None:
        application.dependency_overrides[get_agent_chat_service] = lambda: service
    return TestClient(application), service


def auth_headers(**extra: str) -> dict[str, str]:
    return {"X-User-Code": "EMP-1", "X-User-Roles": "EMPLOYEE", **extra}


def test_send_message_returns_public_contract_and_trusted_identity() -> None:
    service = StubChatService()
    client, _ = build_client(service)

    response = client.post(
        "/api/v1/agent/messages",
        json={
            "conversation_id": "conversation-1",
            "client_message_id": "client-1",
            "content": "你好",
        },
        headers=auth_headers(**{"Idempotency-Key": "idem-1", "X-Request-ID": "request-1"}),
    )

    assert response.status_code == 200
    assert response.json()["data"]["scene"] == "GENERAL_QUERY"
    assert "trace" not in response.text
    assert service.calls[0][2]["actor"].user_code == "EMP-1"
    assert service.calls[0][2]["idempotency_key"] == "idem-1"


def test_history_and_reset_endpoints_use_paginated_contract() -> None:
    service = StubChatService()
    client, _ = build_client(service)

    history = client.get(
        "/api/v1/agent/conversations/conversation-1/messages?page=1&page_size=10",
        headers=auth_headers(),
    )
    reset = client.delete(
        "/api/v1/agent/conversations/conversation-1",
        headers=auth_headers(**{"Idempotency-Key": "reset-1"}),
    )

    assert history.status_code == 200
    assert history.json()["page"] == {"number": 1, "size": 10, "total": 1}
    assert reset.status_code == 200
    assert reset.json()["data"] == {"conversation_id": "conversation-1", "cleared": True}


def test_chat_api_requires_identity_idempotency_and_valid_conversation_id() -> None:
    service = StubChatService()
    client, _ = build_client(service)
    payload = {
        "conversation_id": "invalid conversation",
        "client_message_id": "client-1",
        "content": "",
    }

    unauthenticated = client.post(
        "/api/v1/agent/messages",
        json={**payload, "conversation_id": "conversation-1", "content": "你好"},
        headers={"Idempotency-Key": "idem-1"},
    )
    invalid = client.post(
        "/api/v1/agent/messages",
        json=payload,
        headers=auth_headers(**{"Idempotency-Key": "idem-1"}),
    )
    missing_idempotency = client.post(
        "/api/v1/agent/messages",
        json={**payload, "conversation_id": "conversation-1", "content": "你好"},
        headers=auth_headers(),
    )

    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "UNAUTHENTICATED"
    assert invalid.status_code == 422
    assert missing_idempotency.status_code == 422


def test_unconfigured_agent_returns_safe_503() -> None:
    client, _ = build_client()
    response = client.post(
        "/api/v1/agent/messages",
        json={
            "conversation_id": "conversation-1",
            "client_message_id": "client-1",
            "content": "你好",
        },
        headers=auth_headers(**{"Idempotency-Key": "idem-1"}),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_UNAVAILABLE"
