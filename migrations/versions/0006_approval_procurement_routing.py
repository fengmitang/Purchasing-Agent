"""新增采购申请楼宇路由并兼容非白名单商品采购。

Revision ID: 0006_workflow_routing
Revises: 0005_auth_rbac_foundation
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0006_workflow_routing"
down_revision: str | Sequence[str] | None = "0005_auth_rbac_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """让申请按楼宇进入审批，并允许新商品生成采购单。"""
    with op.batch_alter_table("purchase_requirement") as batch_op:
        batch_op.add_column(sa.Column("building_id", mysql.BIGINT(unsigned=True), nullable=True))
        batch_op.create_index("idx_requirement_building_status", ["building_id", "status"])
        batch_op.create_foreign_key("fk_requirement_building", "building", ["building_id"], ["id"])

    op.alter_column(
        "purchase_order",
        "product_id",
        existing_type=mysql.BIGINT(unsigned=True),
        nullable=True,
    )


def downgrade() -> None:
    """恢复迁移前的商品约束并删除申请楼宇路由。"""
    op.alter_column(
        "purchase_order",
        "product_id",
        existing_type=mysql.BIGINT(unsigned=True),
        nullable=False,
    )
    with op.batch_alter_table("purchase_requirement") as batch_op:
        batch_op.drop_constraint("fk_requirement_building", type_="foreignkey")
        batch_op.drop_index("idx_requirement_building_status")
        batch_op.drop_column("building_id")
