"""认证模块的数据访问层。"""

from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import (
    AuthSession,
    EmployeeBuildingRole,
    Role,
    UserAccount,
    UserLoginIdentifier,
    UserRole,
)
from app.modules.requirement.models import Employee


class AuthRepository:
    """封装账号、角色和会话查询，不在此层作权限决策。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_account_by_identifiers(
        self, normalized_values: set[str], *, for_update: bool = False
    ) -> tuple[UserAccount, Employee] | None:
        statement = (
            select(UserAccount, Employee)
            .join(UserLoginIdentifier, UserLoginIdentifier.account_id == UserAccount.id)
            .join(Employee, Employee.id == UserAccount.employee_id)
            .where(
                UserLoginIdentifier.normalized_value.in_(normalized_values),
                UserLoginIdentifier.status == "ACTIVE",
            )
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        return result.tuples().first()

    async def get_account_employee(self, account_id: int) -> tuple[UserAccount, Employee] | None:
        result = await self._session.execute(
            select(UserAccount, Employee)
            .join(Employee, Employee.id == UserAccount.employee_id)
            .where(UserAccount.id == account_id)
        )
        return result.tuples().first()

    async def list_roles(self, account_id: int, now: datetime) -> frozenset[str]:
        values = await self._session.scalars(
            select(Role.role_code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.account_id == account_id,
                UserRole.valid_from <= now,
                or_(UserRole.valid_to.is_(None), UserRole.valid_to > now),
                Role.status == "ACTIVE",
            )
        )
        return frozenset(values)

    async def list_building_ids(self, employee_id: int, now: datetime) -> frozenset[int]:
        values = await self._session.scalars(
            select(EmployeeBuildingRole.building_id).where(
                EmployeeBuildingRole.employee_id == employee_id,
                EmployeeBuildingRole.valid_from <= now,
                or_(
                    EmployeeBuildingRole.valid_to.is_(None),
                    EmployeeBuildingRole.valid_to > now,
                ),
            )
        )
        return frozenset(values)

    async def get_active_session_by_hash(
        self, token_hash: str, now: datetime
    ) -> AuthSession | None:
        return await self._session.scalar(
            select(AuthSession).where(
                AuthSession.session_token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )

    def add_session(self, auth_session: AuthSession) -> None:
        self._session.add(auth_session)

    async def revoke_session(self, token_hash: str, now: datetime) -> None:
        await self._session.execute(
            update(AuthSession)
            .where(AuthSession.session_token_hash == token_hash, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def revoke_other_sessions(self, account_id: int, now: datetime) -> None:
        await self._session.execute(
            update(AuthSession)
            .where(AuthSession.account_id == account_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
