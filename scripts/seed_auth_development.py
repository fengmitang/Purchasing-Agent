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
        "requirements_routed": 0,
        "timestamps_repaired": 0,
    }
    now = datetime.now(UTC).replace(tzinfo=None)
    try:
        async with transaction_scope(factory) as session:
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != "0006_workflow_routing":
                raise RuntimeError("请先把数据库迁移到 0006_workflow_routing")

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
            for index, building_id in enumerate(buildings):
                result = await session.execute(
                    text(
                        "UPDATE purchase_requirement "
                        "SET building_id = :building_id, updated_at = updated_at "
                        "WHERE building_id IS NULL "
                        "AND source_reference LIKE 'dev-seed-v1:%' "
                        "AND MOD(id - 1, :building_count) = :building_index"
                    ),
                    {
                        "building_id": building_id,
                        "building_count": len(buildings),
                        "building_index": index,
                    },
                )
                counts["requirements_routed"] += max(result.rowcount, 0)
            if buildings:
                result = await session.execute(
                    text(
                        "UPDATE purchase_requirement "
                        "SET building_id = :building_id, updated_at = updated_at "
                        "WHERE building_id IS NULL AND source_reference IS NULL"
                    ),
                    {"building_id": buildings[0]},
                )
                counts["requirements_routed"] += max(result.rowcount, 0)

            # 早期测试数据没有显式写 updated_at，会受 MySQL 服务器本地时区影响。
            # 仅修复带 DEV 标记的测试记录，人工创建的真实申请不会被修改。
            result = await session.execute(
                text(
                    "UPDATE purchase_order AS purchase_order "
                    "JOIN purchase_requirement AS requirement "
                    "ON requirement.id = purchase_order.requirement_id "
                    "SET purchase_order.updated_at = COALESCE("
                    "purchase_order.completed_at, purchase_order.received_at, "
                    "purchase_order.contracted_at, purchase_order.quoted_at, "
                    "purchase_order.purchasing_started_at, purchase_order.created_at) "
                    "WHERE requirement.source_reference LIKE 'dev-seed-v1:%'"
                )
            )
            counts["timestamps_repaired"] += max(result.rowcount, 0)
            result = await session.execute(
                text(
                    "UPDATE purchase_requirement AS requirement "
                    "LEFT JOIN purchase_order AS purchase_order "
                    "ON purchase_order.requirement_id = requirement.id "
                    "LEFT JOIN (SELECT requirement_id, MAX(acted_at) AS acted_at "
                    "FROM purchase_approval GROUP BY requirement_id) AS approval "
                    "ON approval.requirement_id = requirement.id "
                    "SET requirement.updated_at = COALESCE("
                    "purchase_order.updated_at, approval.acted_at, requirement.submitted_at, "
                    "requirement.requested_at, requirement.created_at) "
                    "WHERE requirement.source_reference LIKE 'dev-seed-v1:%'"
                )
            )
            counts["timestamps_repaired"] += max(result.rowcount, 0)

            # 同时纠正早期楼宇回填留下的少量未来时间；仅匹配明显晚于 UTC 当前时间的记录。
            result = await session.execute(
                text(
                    "UPDATE purchase_requirement "
                    "SET updated_at = COALESCE(submitted_at, requested_at, created_at) "
                    "WHERE updated_at > UTC_TIMESTAMP(6) + INTERVAL 1 MINUTE"
                )
            )
            counts["timestamps_repaired"] += max(result.rowcount, 0)
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
