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
