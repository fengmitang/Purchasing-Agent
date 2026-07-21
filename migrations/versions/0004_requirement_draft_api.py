"""支持不完整采购草稿和持久化写入幂等。

Revision ID: 0004_requirement_draft_api
Revises: 0003_procurement_workflow
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0004_requirement_draft_api"
down_revision: str | Sequence[str] | None = "0003_procurement_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    """允许保存部分草稿，并保留重复写入首次成功的结果。"""
    op.alter_column(
        "purchase_requirement",
        "product_name",
        existing_type=sa.String(length=200),
        nullable=True,
    )
    op.create_table(
        "idempotency_record",
        sa.Column(
            "id",
            mysql.BIGINT(unsigned=True),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("actor_code", sa.String(length=50), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("response_payload", mysql.JSON(), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.UniqueConstraint(
            "actor_code",
            "operation",
            "idempotency_key",
            name="uk_idempotency_actor_operation_key",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_idempotency_resource",
        "idempotency_record",
        ["resource_type", "resource_id"],
    )
    op.create_index("idx_idempotency_created_at", "idempotency_record", ["created_at"])


def downgrade() -> None:
    """删除写入重放记录，并恢复设备名称原有非空约束。"""
    op.drop_table("idempotency_record")
    op.alter_column(
        "purchase_requirement",
        "product_name",
        existing_type=sa.String(length=200),
        nullable=False,
    )
