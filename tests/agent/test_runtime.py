from unittest.mock import Mock, patch

from pydantic import SecretStr

from app.config import AgentSettings
from app.modules.agent.runtime import create_agent_runtime


def test_agent_runtime_loads_skills_before_building_service() -> None:
    settings = AgentSettings(
        environment="test",
        agent_enabled=True,
        agent_provider="openai",
        agent_model="test-model",
        agent_api_key=SecretStr("test-key"),
        agent_allow_in_memory=True,
    )
    session_factory = Mock()
    skill_manager = Mock()
    agent_service = Mock()
    client = Mock()

    with (
        patch("openai.AsyncOpenAI", return_value=client),
        patch(
            "app.modules.agent.runtime.SkillManager",
            return_value=skill_manager,
        ),
        patch(
            "app.modules.agent.runtime.build_procurement_agent_service",
            return_value=agent_service,
        ) as build_service,
    ):
        runtime = create_agent_runtime(settings, session_factory)

    assert runtime is not None
    skill_manager.load.assert_called_once_with()
    assert build_service.call_args.kwargs["skill_manager"] is skill_manager


def test_agent_runtime_uses_redis_for_both_chat_and_procurement_sessions() -> None:
    settings = AgentSettings(
        environment="test",
        agent_enabled=True,
        agent_provider="openai",
        agent_model="test-model",
        agent_api_key=SecretStr("test-key"),
        agent_redis_url=SecretStr("redis://localhost:6379/0"),
    )
    session_factory = Mock()
    chat_store = Mock()
    procurement_store = Mock()
    agent_service = Mock()
    client = Mock()

    with (
        patch("openai.AsyncOpenAI", return_value=client),
        patch("app.modules.agent.runtime.RedisAgentChatStore", return_value=chat_store),
        patch(
            "app.modules.agent.runtime.RedisProcurementSessionStore",
            return_value=procurement_store,
        ),
        patch("app.modules.agent.runtime.SkillManager"),
        patch(
            "app.modules.agent.runtime.build_procurement_agent_service",
            return_value=agent_service,
        ) as build_service,
    ):
        runtime = create_agent_runtime(settings, session_factory)

    assert runtime is not None
    assert build_service.call_args.args[2] is procurement_store
    assert chat_store in runtime.resources
    assert procurement_store in runtime.resources
