from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import AgentSettings
from app.infrastructure.database import AsyncSessionFactory
from app.modules.agent.bootstrap import build_procurement_agent_service
from app.modules.agent.chat_service import AgentChatService
from app.modules.agent.chat_store import (
    ChatStoreUnavailable,
    InMemoryAgentChatStore,
    RedisAgentChatStore,
)
from app.modules.agent.intent_service import ModelIntentService
from app.modules.agent.model import (
    AnthropicToolCallingModel,
    OpenAICompatibleToolCallingModel,
)
from app.modules.agent.procurement.service_backend import RequirementServiceBackend
from app.modules.agent.procurement.session_store import InMemoryProcurementSessionStore
from app.modules.agent.skill_loader import SkillManager
from app.modules.requirement.service import RequirementService


@dataclass
class AgentRuntime:
    chat_service: AgentChatService
    resources: tuple[Any, ...] = ()

    async def close(self) -> None:
        for resource in reversed(self.resources):
            close = getattr(resource, "aclose", None) or getattr(resource, "close", None)
            if close is None:
                continue
            result = close()
            if hasattr(result, "__await__"):
                await result


def create_agent_runtime(
    settings: AgentSettings,
    session_factory: AsyncSessionFactory,
) -> AgentRuntime | None:
    if not settings.agent_enabled:
        return None
    if settings.agent_api_key is None:
        return None
    if settings.agent_redis_url is None and not (
        settings.environment in {"local", "test"} and settings.agent_allow_in_memory
    ):
        return None

    resources: list[Any] = []
    if settings.agent_redis_url is not None:
        try:
            store = RedisAgentChatStore(
                settings.agent_redis_url.get_secret_value(),
                ttl_seconds=settings.agent_session_ttl_seconds,
            )
        except ChatStoreUnavailable:
            return None
        resources.append(store)
    else:
        store = InMemoryAgentChatStore()

    api_key = settings.agent_api_key.get_secret_value()
    if settings.agent_provider == "anthropic":
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            return None
        client_options: dict[str, Any] = {"api_key": api_key}
        if settings.agent_base_url:
            client_options["base_url"] = settings.agent_base_url
        try:
            client = AsyncAnthropic(**client_options)
        except Exception:
            return None
        model = AnthropicToolCallingModel(
            client,
            settings.agent_model,
            timeout_seconds=settings.agent_timeout_seconds,
            max_retries=settings.agent_max_retries,
        )
    else:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            return None
        client_options = {"api_key": api_key}
        if settings.agent_base_url:
            client_options["base_url"] = settings.agent_base_url
        try:
            client = AsyncOpenAI(**client_options)
        except Exception:
            return None
        model = OpenAICompatibleToolCallingModel(
            client,
            settings.agent_model,
            timeout_seconds=settings.agent_timeout_seconds,
            max_retries=settings.agent_max_retries,
        )
    resources.append(client)

    backend = RequirementServiceBackend(RequirementService(session_factory))
    skill_manager = SkillManager(str(Path.cwd() / "skills"))
    skill_manager.load()
    agent_service = build_procurement_agent_service(
        backend,
        model,
        InMemoryProcurementSessionStore(),
        skill_manager=skill_manager,
    )
    return AgentRuntime(
        chat_service=AgentChatService(
            agent_service=agent_service,
            intent_service=ModelIntentService(model),
            store=store,
        ),
        resources=tuple(resources),
    )
