import pytest

from app.modules.agent.chat_service import AgentChatService
from app.modules.agent.chat_store import InMemoryAgentChatStore
from app.modules.agent.procurement.schemas import ProcurementSessionState
from app.modules.agent.procurement.session_store import (
    InMemoryProcurementSessionStore,
    RedisProcurementSessionStore,
)
from app.modules.agent.routes import AgentRoute
from app.shared.identity import CurrentUser


@pytest.mark.asyncio
async def test_routes_are_isolated_by_organization_user_and_conversation() -> None:
    store = InMemoryAgentChatStore()
    first = AgentChatService.conversation_key(CurrentUser(user_code="u1", organization_id=1), "c1")
    second = AgentChatService.conversation_key(CurrentUser(user_code="u2", organization_id=1), "c1")
    third = AgentChatService.conversation_key(CurrentUser(user_code="u1", organization_id=2), "c1")

    await store.save_route(first, AgentRoute.PROCUREMENT)
    assert await store.get_route(first) == AgentRoute.PROCUREMENT
    assert await store.get_route(second) is None
    assert await store.get_route(third) is None


@pytest.mark.asyncio
async def test_reset_clears_route_without_affecting_other_conversations() -> None:
    store = InMemoryAgentChatStore()
    first = "1:u1:c1"
    second = "1:u1:c2"
    await store.save_route(first, AgentRoute.PROCUREMENT)
    await store.save_route(second, AgentRoute.GENERAL)

    await store.clear(first)
    assert await store.get_route(first) is None
    assert await store.get_route(second) == AgentRoute.GENERAL


@pytest.mark.asyncio
async def test_procurement_session_clear_isolated_by_organization_user_and_conversation() -> None:
    store = InMemoryProcurementSessionStore()
    state = ProcurementSessionState(
        requirement_id=1,
        requirement_no="PR-1",
        version=1,
        status="DRAFT",
    )
    await store.save(1, "u1", "c1", state)
    await store.save(1, "u1", "c2", state)
    await store.save(1, "u2", "c1", state)
    await store.save(2, "u1", "c1", state)

    await store.clear(1, "u1", "c1")

    assert await store.get(1, "u1", "c1") is None
    assert await store.get(1, "u1", "c2") is not None
    assert await store.get(1, "u2", "c1") is not None
    assert await store.get(2, "u1", "c1") is not None


def test_redis_procurement_session_key_contains_all_tenant_dimensions() -> None:
    assert (
        RedisProcurementSessionStore._key(12, "employee:1", "conversation:1")
        == "procurement:session:12:employee_1:conversation_1"
    )
