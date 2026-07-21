"""身份认证与业务服务共用的 FastAPI 依赖。"""

from typing import Annotated

from fastapi import Header, Request

from app.modules.requirement.service import RequirementService
from app.shared.errors import DomainError, ErrorCode
from app.shared.identity import CurrentUser


async def get_current_user(
    user_code: Annotated[str | None, Header(alias="X-User-Code")] = None,
    roles_header: Annotated[str | None, Header(alias="X-User-Roles")] = None,
) -> CurrentUser:
    """从可信代理请求头解析临时内部身份。"""
    if not user_code or not user_code.strip():
        raise DomainError(ErrorCode.UNAUTHENTICATED, "请先完成身份认证")
    roles = frozenset(
        role.strip().upper() for role in (roles_header or "EMPLOYEE").split(",") if role.strip()
    )
    return CurrentUser(user_code=user_code.strip(), roles=roles or frozenset({"EMPLOYEE"}))


def get_requirement_service(request: Request) -> RequirementService:
    """根据应用基础设施创建请求级采购申请服务。"""
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise DomainError(ErrorCode.INTERNAL_ERROR, "数据库服务尚未配置")
    return RequirementService(session_factory)
