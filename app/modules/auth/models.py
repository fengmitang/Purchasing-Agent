"""登录账号、角色、服务端会话和楼宇职责的 SQLAlchemy 映射。"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class UserAccount(Base):
    """与员工一对一关联的系统登录账号。"""

    __tablename__ = "user_account"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20))
    must_change_password: Mapped[bool] = mapped_column(Boolean)
    failed_login_count: Mapped[int] = mapped_column(Integer)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer)


class UserLoginIdentifier(Base):
    """账号可使用的规范化工号或电话号码。"""

    __tablename__ = "user_login_identifier"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(BigInteger)
    identifier_type: Mapped[str] = mapped_column(String(20))
    normalized_value: Mapped[str] = mapped_column(String(191), unique=True)
    status: Mapped[str] = mapped_column(String(20))


class Role(Base):
    """系统角色字典。"""

    __tablename__ = "role"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_code: Mapped[str] = mapped_column(String(50), unique=True)
    role_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))


class UserRole(Base):
    """账号在有效期内拥有的角色。"""

    __tablename__ = "user_role"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(BigInteger)
    role_id: Mapped[int] = mapped_column(BigInteger)
    valid_from: Mapped[datetime] = mapped_column(DateTime)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime)


class AuthSession(Base):
    """只保存令牌摘要的服务端登录会话。"""

    __tablename__ = "auth_session"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(BigInteger)
    session_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))


class Building(Base):
    """楼长数据范围使用的楼宇主数据。"""

    __tablename__ = "building"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    building_code: Mapped[str] = mapped_column(String(50), unique=True)
    building_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)


class EmployeeBuildingRole(Base):
    """员工在某一楼宇内承担的有效职责。"""

    __tablename__ = "employee_building_role"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger)
    building_id: Mapped[int] = mapped_column(BigInteger)
    role_code: Mapped[str] = mapped_column(String(50))
    valid_from: Mapped[datetime] = mapped_column(DateTime)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime)
