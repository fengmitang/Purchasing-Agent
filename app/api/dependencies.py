"""身份认证与业务服务共用的 FastAPI 依赖。"""

from typing import Annotated

from fastapi import Header, Request

from app.modules.agent.chat_service import AgentChatService
from app.modules.auth.service import AuthService
from app.modules.requirement.service import RequirementService
from app.modules.workflow.service import WorkflowService
from app.shared.errors import DomainError, ErrorCode
from app.shared.identity import CurrentUser


async def get_current_user(
    request: Request,
    user_code: Annotated[str | None, Header(alias="X-User-Code")] = None,
    roles_header: Annotated[str | None, Header(alias="X-User-Roles")] = None,
) -> CurrentUser:
    """优先从服务端会话认证，仅在本地测试环境兼容临时身份请求头。"""
    settings = request.app.state.runtime_settings
    token = request.cookies.get(settings.auth_session_cookie_name)
    if token:
        return await get_auth_service(request).authenticate_session(token)
    if not settings.allow_dev_identity_headers or settings.environment == "production":
        raise DomainError(ErrorCode.UNAUTHENTICATED, "请先登录")
    if not user_code or not user_code.strip():
        raise DomainError(ErrorCode.UNAUTHENTICATED, "请先登录")
    roles = frozenset(
        role.strip().upper() for role in (roles_header or "EMPLOYEE").split(",") if role.strip()
    )
    return CurrentUser(user_code=user_code.strip(), roles=roles or frozenset({"EMPLOYEE"}))


def get_auth_service(request: Request) -> AuthService:
    """根据应用配置创建请求级认证服务。"""
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise DomainError(ErrorCode.INTERNAL_ERROR, "数据库服务尚未配置")
    settings = request.app.state.runtime_settings
    return AuthService(
        session_factory,
        session_ttl_seconds=settings.auth_session_ttl_seconds,
    )


def get_requirement_service(request: Request) -> RequirementService:
    """根据应用基础设施创建请求级采购申请服务。"""
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise DomainError(ErrorCode.INTERNAL_ERROR, "数据库服务尚未配置")
    return RequirementService(session_factory)


def get_workflow_service(request: Request) -> WorkflowService:
    """根据应用基础设施创建请求级审批采购工作流服务。"""
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise DomainError(ErrorCode.INTERNAL_ERROR, "数据库服务尚未配置")
    return WorkflowService(session_factory)


def get_agent_chat_service(request: Request) -> AgentChatService:
    service = getattr(request.app.state, "agent_chat_service", None)
    if service is None:
        raise DomainError(ErrorCode.AGENT_UNAVAILABLE, "Agent 服务尚未配置")
    return service
