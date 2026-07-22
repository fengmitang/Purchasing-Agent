"""新增登录账号、角色、服务端会话和楼宇权限基础。

Revision ID: 0005_auth_rbac_foundation
Revises: 0004_requirement_draft_api
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0005_auth_rbac_foundation"
down_revision: str | Sequence[str] | None = "0004_requirement_draft_api"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def _id_column() -> sa.Column:
    return sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True)


def _created_at_column() -> sa.Column:
    return sa.Column(
        "created_at",
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP(6)"),
    )


def _updated_at_column() -> sa.Column:
    return sa.Column(
        "updated_at",
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
    )


def upgrade() -> None:
    """建立认证与角色授权的持久化基础。"""
    op.create_table(
        "user_account",
        _id_column(),
        sa.Column("employee_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("locked_until", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("password_changed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("last_login_at", mysql.DATETIME(fsp=6), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("employee_id", name="uk_user_account_employee"),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"], name="fk_account_employee"),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_account_status", "user_account", ["status"])

    op.create_table(
        "user_login_identifier",
        _id_column(),
        sa.Column("account_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("identifier_type", sa.String(length=20), nullable=False),
        sa.Column("normalized_value", sa.String(length=191), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("verified_at", mysql.DATETIME(fsp=6), nullable=True),
        _created_at_column(),
        sa.UniqueConstraint("normalized_value", name="uk_login_identifier_value"),
        sa.UniqueConstraint(
            "account_id", "identifier_type", name="uk_login_identifier_account_type"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["user_account.id"], name="fk_login_identifier_account"
        ),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "role",
        _id_column(),
        sa.Column("role_code", sa.String(length=50), nullable=False),
        sa.Column("role_name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        _created_at_column(),
        _updated_at_column(),
        sa.UniqueConstraint("role_code", name="uk_role_code"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "user_role",
        _id_column(),
        sa.Column("account_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("role_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column(
            "valid_from",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column("valid_to", mysql.DATETIME(fsp=6), nullable=True),
        _created_at_column(),
        sa.UniqueConstraint("account_id", "role_id", name="uk_user_role_account_role"),
        sa.ForeignKeyConstraint(["account_id"], ["user_account.id"], name="fk_user_role_account"),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], name="fk_user_role_role"),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_user_role_validity", "user_role", ["account_id", "valid_to"])

    op.create_table(
        "auth_session",
        _id_column(),
        sa.Column("account_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("last_seen_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("revoked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.UniqueConstraint("session_token_hash", name="uk_auth_session_token_hash"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["user_account.id"], name="fk_auth_session_account"
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_auth_session_account_active",
        "auth_session",
        ["account_id", "revoked_at", "expires_at"],
    )

    op.create_table(
        "building",
        _id_column(),
        sa.Column("building_code", sa.String(length=50), nullable=False),
        sa.Column("building_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        _created_at_column(),
        _updated_at_column(),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("building_code", name="uk_building_code"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "employee_building_role",
        _id_column(),
        sa.Column("employee_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("building_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("role_code", sa.String(length=50), nullable=False),
        sa.Column(
            "valid_from",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column("valid_to", mysql.DATETIME(fsp=6), nullable=True),
        _created_at_column(),
        sa.UniqueConstraint(
            "employee_id", "building_id", "role_code", name="uk_employee_building_role"
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employee.id"], name="fk_employee_building_role_employee"
        ),
        sa.ForeignKeyConstraint(
            ["building_id"], ["building.id"], name="fk_employee_building_role_building"
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_employee_building_role_scope",
        "employee_building_role",
        ["role_code", "building_id", "valid_to"],
    )

    role_table = sa.table(
        "role",
        sa.column("role_code", sa.String()),
        sa.column("role_name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("status", sa.String()),
    )
    op.bulk_insert(
        role_table,
        [
            {
                "role_code": "EMPLOYEE",
                "role_name": "普通员工",
                "description": "创建、修改和查看本人采购申请",
                "status": "ACTIVE",
            },
            {
                "role_code": "BUILDING_MANAGER",
                "role_name": "楼长（专业工程师）",
                "description": "查看并审批职责楼宇内的采购申请",
                "status": "ACTIVE",
            },
            {
                "role_code": "PURCHASER",
                "role_name": "采购员",
                "description": "处理审批通过后的采购任务并登记入库",
                "status": "ACTIVE",
            },
            {
                "role_code": "ADMIN",
                "role_name": "系统管理员",
                "description": "管理账号、角色和业务基础数据",
                "status": "ACTIVE",
            },
        ],
    )


def downgrade() -> None:
    """删除认证与楼宇权限基础表。"""
    op.drop_table("employee_building_role")
    op.drop_table("building")
    op.drop_table("auth_session")
    op.drop_table("user_role")
    op.drop_table("role")
    op.drop_table("user_login_identifier")
    op.drop_table("user_account")
