"""传入业务服务的已认证用户与审计上下文。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """当前内部身份适配器使用的最小认证身份。"""

    user_code: str
    roles: frozenset[str] = frozenset({"EMPLOYEE"})
    account_id: int | None = None
    employee_id: int | None = None
    name: str | None = None
    phone: str | None = None
    must_change_password: bool = False
    organization_id: int = 0
    building_ids: frozenset[int] = frozenset()


@dataclass(frozen=True, slots=True)
class AuditContext:
    """状态变更服务所需的请求元数据。"""

    actor: CurrentUser
    request_id: str
    idempotency_key: str
    source_ip: str | None = None
