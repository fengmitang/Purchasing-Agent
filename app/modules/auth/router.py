"""网页登录、退出、当前用户和修改密码接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.dependencies import get_auth_service, get_current_user
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    CurrentUserView,
    LoginRequest,
    LoginResult,
    MessageResult,
)
from app.modules.auth.service import AuthService
from app.shared.identity import CurrentUser
from app.shared.responses import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/api/v1/auth", tags=["登录与账号"])


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    settings = request.app.state.runtime_settings
    response.set_cookie(
        key=settings.auth_session_cookie_name,
        value=token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        path="/",
    )


def _clear_session_cookie(response: Response, request: Request) -> None:
    settings = request.app.state.runtime_settings
    response.delete_cookie(
        key=settings.auth_session_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        path="/",
    )


@router.post(
    "/login",
    response_model=SuccessResponse[LoginResult],
    summary="员工登录",
    description="使用员工工号或已登记联系电话加密码登录。成功后浏览器自动保存安全会话 Cookie。",
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SuccessResponse[LoginResult]:
    client_host = request.client.host if request.client else None
    token, user = await service.login(
        identifier=payload.identifier,
        password=payload.password,
        source_ip=client_host,
        user_agent=request.headers.get("User-Agent"),
    )
    _set_session_cookie(response, request, token)
    return SuccessResponse(
        data=LoginResult(user=user),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@router.get(
    "/me",
    response_model=SuccessResponse[CurrentUserView],
    summary="查看当前登录员工",
    description="页面刷新后用此接口恢复员工姓名、工号、角色和楼宇权限范围。",
)
async def me(
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SuccessResponse[CurrentUserView]:
    return SuccessResponse(
        data=service.current_user_view(actor),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@router.post(
    "/logout",
    response_model=SuccessResponse[MessageResult],
    summary="退出登录",
    description="撤销当前服务端会话并清除浏览器登录 Cookie。",
)
async def logout(
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SuccessResponse[MessageResult]:
    settings = request.app.state.runtime_settings
    await service.logout(request.cookies.get(settings.auth_session_cookie_name))
    _clear_session_cookie(response, request)
    return SuccessResponse(
        data=MessageResult(message="已安全退出"),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@router.post(
    "/change-password",
    response_model=SuccessResponse[MessageResult],
    summary="修改本人密码",
    description="校验当前密码后设置新密码，并撤销该账号的全部登录会话，需要重新登录。",
)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SuccessResponse[MessageResult]:
    await service.change_password(
        actor,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    _clear_session_cookie(response, request)
    return SuccessResponse(
        data=MessageResult(message="密码已修改，请重新登录"),
        meta=ResponseMeta(request_id=request.state.request_id),
    )
