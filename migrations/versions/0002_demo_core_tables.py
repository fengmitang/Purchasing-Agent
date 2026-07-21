"""Create the ten core tables for the Demo MVP.

Revision ID: 0002_demo_core_tables
Revises: 0001_database_baseline
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0002_demo_core_tables"
down_revision: str | Sequence[str] | None = "0001_database_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def _id_column() -> sa.Column:
    return sa.Column(
        "id",
        mysql.BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )


def _created_at_column() -> sa.Column:
    return sa.Column(
        "created_at",
        mysql.DATETIME(),
        nullable=True,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


def upgrade() -> None:
    """Create the Demo MVP product, Agent, recommendation, and order tables."""
    op.create_table(
        "product_category",
        _id_column(),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        _created_at_column(),
        sa.UniqueConstraint("name", name="uk_category_name"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "product_whitelist",
        _id_column(),
        sa.Column("category_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("specification", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True, server_default="ACTIVE"),
        _created_at_column(),
        sa.Column(
            "updated_at",
            mysql.DATETIME(),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        **TABLE_OPTIONS,
    )
    op.create_index("category_id", "product_whitelist", ["category_id"])
    op.create_index("idx_brand_model", "product_whitelist", ["brand", "model"])
    op.create_index("idx_product_name", "product_whitelist", ["product_name"])
    op.create_foreign_key(
        "product_whitelist_ibfk_1",
        "product_whitelist",
        "product_category",
        ["category_id"],
        ["id"],
    )

    op.create_table(
        "supplier",
        _id_column(),
        sa.Column("supplier_name", sa.String(length=200), nullable=False),
        sa.Column("contact", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("level", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True, server_default="ACTIVE"),
        _created_at_column(),
        sa.UniqueConstraint("supplier_name", name="uk_supplier_name"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "product_supplier",
        _id_column(),
        sa.Column("product_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("supplier_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("delivery_days", sa.Integer(), nullable=True),
        _created_at_column(),
        sa.UniqueConstraint("product_id", "supplier_id", name="uk_product_supplier"),
        **TABLE_OPTIONS,
    )
    op.create_index("supplier_id", "product_supplier", ["supplier_id"])
    op.create_foreign_key(
        "product_supplier_ibfk_1",
        "product_supplier",
        "product_whitelist",
        ["product_id"],
        ["id"],
    )
    op.create_foreign_key(
        "product_supplier_ibfk_2",
        "product_supplier",
        "supplier",
        ["supplier_id"],
        ["id"],
    )

    op.create_table(
        "agent_session",
        _id_column(),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=True, server_default="ACTIVE"),
        _created_at_column(),
        sa.UniqueConstraint("session_id", name="uk_session_id"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "agent_message",
        _id_column(),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        _created_at_column(),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_session", "agent_message", ["session_id"])

    op.create_table(
        "purchase_requirement",
        _id_column(),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("specification", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=True, server_default="CREATED"),
        _created_at_column(),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_requirement_product", "purchase_requirement", ["product_name"])

    op.create_table(
        "recommendation",
        _id_column(),
        sa.Column("requirement_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("product_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("supplier_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=True, server_default=sa.text("0")),
        _created_at_column(),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_requirement", "recommendation", ["requirement_id"])
    op.create_index("product_id", "recommendation", ["product_id"])
    op.create_index("supplier_id", "recommendation", ["supplier_id"])
    op.create_foreign_key(
        "recommendation_ibfk_1",
        "recommendation",
        "purchase_requirement",
        ["requirement_id"],
        ["id"],
    )
    op.create_foreign_key(
        "recommendation_ibfk_2",
        "recommendation",
        "product_whitelist",
        ["product_id"],
        ["id"],
    )
    op.create_foreign_key(
        "recommendation_ibfk_3",
        "recommendation",
        "supplier",
        ["supplier_id"],
        ["id"],
    )

    op.create_table(
        "purchase_order",
        _id_column(),
        sa.Column("order_no", sa.String(length=100), nullable=False),
        sa.Column("requirement_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("product_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("supplier_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=True, server_default="CREATED"),
        _created_at_column(),
        sa.UniqueConstraint("order_no", name="uk_order_no"),
        **TABLE_OPTIONS,
    )
    op.create_index("product_id", "purchase_order", ["product_id"])
    op.create_index("requirement_id", "purchase_order", ["requirement_id"])
    op.create_index("supplier_id", "purchase_order", ["supplier_id"])
    op.create_foreign_key(
        "purchase_order_ibfk_1",
        "purchase_order",
        "purchase_requirement",
        ["requirement_id"],
        ["id"],
    )
    op.create_foreign_key(
        "purchase_order_ibfk_2",
        "purchase_order",
        "product_whitelist",
        ["product_id"],
        ["id"],
    )
    op.create_foreign_key(
        "purchase_order_ibfk_3",
        "purchase_order",
        "supplier",
        ["supplier_id"],
        ["id"],
    )

    op.create_table(
        "operation_log",
        _id_column(),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("operator", sa.String(length=100), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        _created_at_column(),
        **TABLE_OPTIONS,
    )


def downgrade() -> None:
    """Drop the Demo MVP tables in reverse dependency order."""
    op.drop_table("operation_log")
    op.drop_table("purchase_order")
    op.drop_table("recommendation")
    op.drop_table("purchase_requirement")
    op.drop_table("agent_message")
    op.drop_table("agent_session")
    op.drop_table("product_supplier")
    op.drop_table("supplier")
    op.drop_table("product_whitelist")
    op.drop_table("product_category")
