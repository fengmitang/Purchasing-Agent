"""为本地 DEV 测试员工建立登录账号、角色和楼长楼宇范围。"""

import asyncio
import os
from datetime import UTC, datetime

from sqlalchemy import text

from app.config import Settings
from app.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    transaction_scope,
)
from app.modules.auth.security import hash_password

DEFAULT_TEST_PASSWORD = "ChangeMe2026!"


async def seed_auth() -> dict[str, int]:
    """幂等创建开发账号；不会为非 DEV 员工擅自建立账号。"""
    settings = Settings()
    if settings.environment not in {"local", "test"}:
        raise RuntimeError("登录测试账号只能写入 local 或 test 环境")
    password = os.getenv("DEV_SEED_PASSWORD", DEFAULT_TEST_PASSWORD)
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    counts = {
        "accounts": 0,
        "identifiers": 0,
        "roles": 0,
        "buildings": 0,
        "scopes": 0,
        "first_login_flags_cleared": 0,
    }
    now = datetime.now(UTC).replace(tzinfo=None)
    try:
        async with transaction_scope(factory) as session:
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != "0005_auth_rbac_foundation":
                raise RuntimeError("请先把数据库迁移到 0005_auth_rbac_foundation")

            role_rows = (
                await session.execute(
                    text("SELECT id, role_code FROM role WHERE status = 'ACTIVE'")
                )
            ).all()
            role_ids = {str(code): int(role_id) for role_id, code in role_rows}
            employees = (
                (
                    await session.execute(
                        text(
                            "SELECT id, employee_no, name, phone, role FROM employee "
                            "WHERE employee_no LIKE 'DEV-%' AND status = 'ACTIVE' ORDER BY id"
                        )
                    )
                )
                .mappings()
                .all()
            )
            if not employees:
                raise RuntimeError("没有找到 DEV 测试员工，请先执行开发数据脚本")

            result = await session.execute(
                text(
                    "UPDATE user_account AS account "
                    "JOIN employee ON employee.id = account.employee_id "
                    "SET account.must_change_password = 0 "
                    "WHERE employee.employee_no LIKE 'DEV-%' "
                    "AND account.must_change_password <> 0"
                )
            )
            counts["first_login_flags_cleared"] = max(result.rowcount, 0)

            for employee in employees:
                account_id = await session.scalar(
                    text("SELECT id FROM user_account WHERE employee_id = :employee_id"),
                    {"employee_id": employee["id"]},
                )
                if account_id is None:
                    result = await session.execute(
                        text(
                            "INSERT INTO user_account "
                            "(employee_id, password_hash, status, must_change_password, "
                            "failed_login_count, version) "
                            "VALUES (:employee_id, :password_hash, 'ACTIVE', 0, 0, 1)"
                        ),
                        {
                            "employee_id": employee["id"],
                            "password_hash": hash_password(password),
                        },
                    )
                    account_id = int(result.lastrowid)
                    counts["accounts"] += 1

                identifiers = [("EMPLOYEE_NO", str(employee["employee_no"]).strip().upper())]
                if employee["phone"]:
                    identifiers.append(("PHONE", str(employee["phone"]).strip()))
                for identifier_type, normalized_value in identifiers:
                    result = await session.execute(
                        text(
                            "INSERT IGNORE INTO user_login_identifier "
                            "(account_id, identifier_type, normalized_value, status, verified_at) "
                            "VALUES (:account_id, :identifier_type, :normalized_value, "
                            "'ACTIVE', :now)"
                        ),
                        {
                            "account_id": account_id,
                            "identifier_type": identifier_type,
                            "normalized_value": normalized_value,
                            "now": now,
                        },
                    )
                    counts["identifiers"] += max(result.rowcount, 0)

                employee_roles = ["EMPLOYEE"]
                if employee["role"] == "APPROVER":
                    employee_roles.append("BUILDING_MANAGER")
                elif employee["role"] == "PURCHASER":
                    employee_roles.append("PURCHASER")
                for role_code in employee_roles:
                    result = await session.execute(
                        text(
                            "INSERT IGNORE INTO user_role (account_id, role_id, valid_from) "
                            "VALUES (:account_id, :role_id, :now)"
                        ),
                        {"account_id": account_id, "role_id": role_ids[role_code], "now": now},
                    )
                    counts["roles"] += max(result.rowcount, 0)

            for index in range(8):
                result = await session.execute(
                    text(
                        "INSERT IGNORE INTO building "
                        "(building_code, building_name, status, version) "
                        "VALUES (:code, :name, 'ACTIVE', 1)"
                    ),
                    {"code": f"DEV-B{index + 1:02d}", "name": f"测试楼宇 {index + 1} 号"},
                )
                counts["buildings"] += max(result.rowcount, 0)

            managers = [row for row in employees if row["role"] == "APPROVER"]
            buildings = (
                (
                    await session.execute(
                        text(
                            "SELECT id FROM building WHERE building_code LIKE 'DEV-B%' ORDER BY id"
                        )
                    )
                )
                .scalars()
                .all()
            )
            for employee, building_id in zip(managers, buildings, strict=False):
                result = await session.execute(
                    text(
                        "INSERT IGNORE INTO employee_building_role "
                        "(employee_id, building_id, role_code, valid_from) "
                        "VALUES (:employee_id, :building_id, 'BUILDING_MANAGER', :now)"
                    ),
                    {"employee_id": employee["id"], "building_id": building_id, "now": now},
                )
                counts["scopes"] += max(result.rowcount, 0)
        return counts
    finally:
        await engine.dispose()


def main() -> None:
    counts = asyncio.run(seed_auth())
    print("登录测试数据写入完成：" + "，".join(f"{key}={value}" for key, value in counts.items()))
    print("测试账号示例：DEV-E0001、DEV-A0001、DEV-P0001")
    print("测试密码来自 DEV_SEED_PASSWORD；未设置时为 ChangeMe2026!。")


if __name__ == "__main__":
    main()
