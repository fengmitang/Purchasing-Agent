import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import redis.asyncio as redis

from app.modules.agent.chat_schemas import (
    ChatHistoryMessage,
    ChatMessageStatus,
)
from app.modules.agent.chat_store import RedisAgentChatStore
from app.modules.agent.procurement.schemas import ProcurementSessionState
from app.modules.agent.procurement.session_store import RedisProcurementSessionStore
from app.modules.agent.routes import AgentRoute

REDIS_URL = os.getenv("TEST_REDIS_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL is not configured"),
]


async def test_real_redis_session_round_trip_ttl_isolation_and_clear() -> None:
    suffix = uuid4().hex
    conversation_key = f"91:redis-user:{suffix}"
    conversation_id = f"conversation-{suffix}"
    chat_store = RedisAgentChatStore(REDIS_URL, ttl_seconds=30)
    procurement_store = RedisProcurementSessionStore(REDIS_URL, ttl_seconds=30)
    client = redis.from_url(REDIS_URL, decode_responses=True)
    procurement_key = RedisProcurementSessionStore._key(
        91,
        "redis-user",
        conversation_id,
    )
    other_org_key = RedisProcurementSessionStore._key(
        92,
        "redis-user",
        conversation_id,
    )
    try:
        state = ProcurementSessionState(
            requirement_id=901,
            requirement_no="PR-REDIS-901",
            version=3,
            status="DRAFT",
        )
        await procurement_store.save(91, "redis-user", conversation_id, state)
        await procurement_store.save(92, "redis-user", conversation_id, state)
        await chat_store.save_route(conversation_key, AgentRoute.PROCUREMENT)
        await chat_store.append_message(
            conversation_key,
            ChatHistoryMessage(
                message_id="redis-message",
                role="USER",
                content="真实 Redis 集成测试",
                status=ChatMessageStatus.COMPLETED,
                created_at=datetime.now(UTC),
            ),
        )
        await chat_store.save_idempotency(
            conversation_key,
            "redis-idempotency",
            "request-hash",
            {"ok": True},
        )

        loaded = await procurement_store.get(91, "redis-user", conversation_id)
        assert loaded == state
        assert await procurement_store.get(92, "redis-user", conversation_id) == state
        assert 0 < await client.ttl(procurement_key) <= 30
        assert await chat_store.get_route(conversation_key) == AgentRoute.PROCUREMENT
        assert [item.message_id for item in await chat_store.list_messages(conversation_key)] == [
            "redis-message"
        ]
        assert await chat_store.get_idempotency(conversation_key, "redis-idempotency") == (
            "request-hash",
            {"ok": True},
        )

        await procurement_store.clear(91, "redis-user", conversation_id)
        await chat_store.clear(conversation_key)

        assert await procurement_store.get(91, "redis-user", conversation_id) is None
        assert await procurement_store.get(92, "redis-user", conversation_id) == state
        assert await chat_store.get_route(conversation_key) is None
        assert await chat_store.list_messages(conversation_key) == []
        assert await chat_store.get_idempotency(conversation_key, "redis-idempotency") is None
    finally:
        await client.delete(
            procurement_key,
            other_org_key,
            RedisAgentChatStore._messages_key(conversation_key),
            RedisAgentChatStore._route_key(conversation_key),
            RedisAgentChatStore._idempotency_key(
                conversation_key,
                "redis-idempotency",
            ),
            RedisAgentChatStore._idempotency_index_key(conversation_key),
        )
        await client.aclose()
        await procurement_store.close()
        await chat_store.close()
