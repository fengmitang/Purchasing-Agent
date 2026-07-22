"""Application assembly for the modular monolith."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.health import router as health_router
from app.api.middleware import RequestContextMiddleware
from app.config import AgentSettings, RuntimeSettings, Settings
from app.infrastructure.database import (
    AsyncSessionFactory,
    create_database_engine,
    create_session_factory,
)
from app.infrastructure.logging import configure_logging
from app.modules.agent.router import router as agent_router
from app.modules.agent.runtime import create_agent_runtime
from app.modules.requirement.router import recommendation_router
from app.modules.requirement.router import router as requirement_router
from app.shared.constants import APP_VERSION
from app.shared.errors import DomainError
from app.shared.exception_handlers import (
    domain_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)


def create_application(session_factory: AsyncSessionFactory | None = None) -> FastAPI:
    """Build a new FastAPI application instance."""
    runtime_settings = RuntimeSettings()
    configure_logging(runtime_settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.agent_chat_service = None
        if session_factory is not None:
            active_session_factory = session_factory
            engine = None
        else:
            try:
                settings = Settings()
            except ValueError:
                yield
                return

            engine = create_database_engine(settings)
            active_session_factory = create_session_factory(engine)

        application.state.session_factory = active_session_factory
        agent_runtime = create_agent_runtime(AgentSettings(), active_session_factory)
        if agent_runtime is not None:
            application.state.agent_chat_service = agent_runtime.chat_service
        try:
            yield
        finally:
            if agent_runtime is not None:
                await agent_runtime.close()
            if engine is not None:
                await engine.dispose()

    application = FastAPI(
        title="数据中心采购 Agent 后端接口",
        description=(
            "供员工端、Agent、楼长审批端和采购端调用的后端接口。"
            "当前页面可直接创建采购草稿、修改草稿、查询历史供应商并提交审批。"
        ),
        version=APP_VERSION,
        lifespan=lifespan,
    )
    application.add_middleware(RequestContextMiddleware)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(DomainError, domain_exception_handler)
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.include_router(health_router)
    application.include_router(requirement_router)
    application.include_router(recommendation_router)
    application.include_router(agent_router)
    return application
