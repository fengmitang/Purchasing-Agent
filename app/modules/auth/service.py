"""登录、服务端会话和密码修改的业务规则与事务边界。"""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.infrastructure.database import AsyncSessionFactory, transaction_scope
from app.modules.auth.models import AuthSession
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import CurrentUserView
from app.modules.auth.security import (
    hash_password,
    hash_session_token,
    normalize_identifiers,
    validate_new_password,
    verify_password,
)
from app.shared.errors import DomainError, ErrorCode
from app.shared.identity import CurrentUser

_DUMMY_PASSWORD_HASH = hash_password("Not-A-Real-Account-Password-2026")


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


class AuthService:
    """对外提供不泄露账号状态细节的登录和会话能力。"""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        session_ttl_seconds: int = 28_800,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._session_ttl = timedelta(seconds=session_ttl_seconds)
        self._clock = clock or (lambda: datetime.now(UTC))

    async def login(
        self,
        *,
        identifier: str,
        password: str,
        source_ip: str | None,
        user_agent: str | None,
    ) -> tuple[str, CurrentUserView]:
        """校验工号或电话与密码，成功后建立只存摘要的服务端会话。"""
        now = _utc_naive(self._clock())
        invalid_credentials = False
        async with transaction_scope(self._session_factory) as session:
            repository = AuthRepository(session)
            pair = await repository.get_account_by_identifiers(
                normalize_identifiers(identifier), for_update=True
            )
            if pair is None:
                verify_password(_DUMMY_PASSWORD_HASH, password)
                raise self._invalid_credentials()

            account, employee = pair
            is_locked = account.locked_until is not None and account.locked_until > now
            if (
                account.status != "ACTIVE"
                or employee.status != "ACTIVE"
                or is_locked
                or not verify_password(account.password_hash, password)
            ):
                if account.status == "ACTIVE" and employee.status == "ACTIVE" and not is_locked:
                    account.failed_login_count += 1
                    if account.failed_login_count >= 5:
                        account.locked_until = now + timedelta(minutes=15)
                        account.failed_login_count = 0
                    account.version += 1
                invalid_credentials = True
            else:
                account.failed_login_count = 0
                account.locked_until = None
                account.last_login_at = now
                account.version += 1
                token = secrets.token_urlsafe(32)
                repository.add_session(
                    AuthSession(
                        account_id=account.id,
                        session_token_hash=hash_session_token(token),
                        created_at=now,
                        expires_at=now + self._session_ttl,
                        last_seen_at=now,
                        revoked_at=None,
                        ip_address=source_ip,
                        user_agent=(user_agent or "")[:500] or None,
                    )
                )
                roles = await repository.list_roles(account.id, now)
                buildings = await repository.list_building_ids(employee.id, now)
                result = token, self._view(account, employee, roles, buildings)
        if invalid_credentials:
            raise self._invalid_credentials()
        return result

    async def authenticate_session(self, token: str) -> CurrentUser:
        """从有效服务端会话恢复当前员工及其最新角色和楼宇范围。"""
        now = _utc_naive(self._clock())
        async with transaction_scope(self._session_factory) as session:
            repository = AuthRepository(session)
            auth_session = await repository.get_active_session_by_hash(
                hash_session_token(token), now
            )
            if auth_session is None:
                raise DomainError(ErrorCode.UNAUTHENTICATED, "登录已失效，请重新登录")
            pair = await repository.get_account_employee(auth_session.account_id)
            if pair is None:
                raise DomainError(ErrorCode.UNAUTHENTICATED, "登录已失效，请重新登录")
            account, employee = pair
            if account.status != "ACTIVE" or employee.status != "ACTIVE":
                raise DomainError(ErrorCode.UNAUTHENTICATED, "登录已失效，请重新登录")
            roles = await repository.list_roles(account.id, now)
            buildings = await repository.list_building_ids(employee.id, now)
            auth_session.last_seen_at = now
            return CurrentUser(
                user_code=employee.employee_no or str(employee.id),
                roles=roles or frozenset({"EMPLOYEE"}),
                account_id=account.id,
                employee_id=employee.id,
                name=employee.name,
                phone=employee.phone,
                must_change_password=account.must_change_password,
                building_ids=buildings,
            )

    async def logout(self, token: str | None) -> None:
        """撤销当前会话；重复退出同样视为成功。"""
        if not token:
            return
        now = _utc_naive(self._clock())
        async with transaction_scope(self._session_factory) as session:
            await AuthRepository(session).revoke_session(hash_session_token(token), now)

    async def change_password(
        self, actor: CurrentUser, *, current_password: str, new_password: str
    ) -> None:
        """修改本人密码并撤销全部登录会话。"""
        if actor.account_id is None:
            raise DomainError(ErrorCode.FORBIDDEN, "临时开发身份不能修改登录密码")
        try:
            validate_new_password(new_password)
        except ValueError as exc:
            raise DomainError(ErrorCode.VALIDATION_ERROR, str(exc)) from exc
        if current_password == new_password:
            raise DomainError(ErrorCode.VALIDATION_ERROR, "新密码不能与当前密码相同")

        now = _utc_naive(self._clock())
        async with transaction_scope(self._session_factory) as session:
            repository = AuthRepository(session)
            pair = await repository.get_account_employee(actor.account_id)
            if pair is None or not verify_password(pair[0].password_hash, current_password):
                raise DomainError(ErrorCode.VALIDATION_ERROR, "当前密码不正确")
            account, _ = pair
            account.password_hash = hash_password(new_password)
            account.must_change_password = False
            account.password_changed_at = now
            account.failed_login_count = 0
            account.locked_until = None
            account.version += 1
            await repository.revoke_other_sessions(account.id, now)

    @staticmethod
    def current_user_view(actor: CurrentUser) -> CurrentUserView:
        """将内部身份转换为前端可安全读取的个人信息。"""
        if actor.account_id is None or actor.employee_id is None or actor.name is None:
            raise DomainError(ErrorCode.FORBIDDEN, "当前身份不是网页登录账号")
        return CurrentUserView(
            account_id=actor.account_id,
            employee_id=actor.employee_id,
            employee_no=actor.user_code,
            name=actor.name,
            phone=actor.phone,
            roles=sorted(actor.roles),
            building_ids=sorted(actor.building_ids),
            must_change_password=actor.must_change_password,
        )

    @staticmethod
    def _view(account, employee, roles, buildings) -> CurrentUserView:
        return CurrentUserView(
            account_id=account.id,
            employee_id=employee.id,
            employee_no=employee.employee_no or str(employee.id),
            name=employee.name,
            phone=employee.phone,
            roles=sorted(roles or {"EMPLOYEE"}),
            building_ids=sorted(buildings),
            must_change_password=account.must_change_password,
        )

    @staticmethod
    def _invalid_credentials() -> DomainError:
        return DomainError(ErrorCode.UNAUTHENTICATED, "工号、电话或密码不正确")
