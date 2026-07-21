"""Add employees, approval workflow, and procurement completion tracking.

Revision ID: 0003_procurement_workflow
Revises: 0002_demo_core_tables
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0003_procurement_workflow"
down_revision: str | Sequence[str] | None = "0002_demo_core_tables"
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
    """Extend the Demo schema with the confirmed approval and purchasing workflow."""
    op.create_table(
        "employee",
        _id_column(),
        sa.Column("employee_no", sa.String(length=50), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        _created_at_column(),
        _updated_at_column(),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("employee_no", name="uk_employee_no"),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_employee_name", "employee", ["name"])
    op.create_index("idx_employee_phone", "employee", ["phone"])

    # Imported historical rows can legitimately lack a category, Agent session, or
    # machine-readable quantity. Keep the raw values on the requirement instead of
    # inventing business data.
    op.alter_column(
        "product_whitelist",
        "category_id",
        existing_type=mysql.BIGINT(unsigned=True),
        nullable=True,
    )
    op.alter_column(
        "purchase_requirement",
        "session_id",
        existing_type=sa.String(length=100),
        nullable=True,
    )
    op.alter_column(
        "purchase_requirement",
        "quantity",
        existing_type=sa.Numeric(precision=10, scale=2),
        type_=sa.Numeric(precision=18, scale=4),
        nullable=True,
    )

    with op.batch_alter_table("purchase_requirement") as batch_op:
        batch_op.add_column(sa.Column("requirement_no", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("employee_id", mysql.BIGINT(unsigned=True), nullable=True))
        batch_op.add_column(sa.Column("applicant_employee_no", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("applicant_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("applicant_phone", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("requested_at", mysql.DATETIME(fsp=6), nullable=True))
        batch_op.add_column(sa.Column("submitted_at", mysql.DATETIME(fsp=6), nullable=True))
        batch_op.add_column(
            sa.Column("revision_no", sa.Integer(), nullable=False, server_default=sa.text("1"))
        )
        batch_op.add_column(
            sa.Column("previous_requirement_id", mysql.BIGINT(unsigned=True), nullable=True)
        )
        batch_op.add_column(sa.Column("category_id", mysql.BIGINT(unsigned=True), nullable=True))
        batch_op.add_column(sa.Column("category_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("application_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("application_location", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("device_type", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("product_id", mysql.BIGINT(unsigned=True), nullable=True))
        batch_op.add_column(sa.Column("product_full_name", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("quantity_raw", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("supplier_id", mysql.BIGINT(unsigned=True), nullable=True))
        batch_op.add_column(sa.Column("supplier_name", sa.String(length=200), nullable=True))
        batch_op.add_column(
            sa.Column("unit_price", sa.Numeric(precision=18, scale=2), nullable=True)
        )
        batch_op.add_column(sa.Column("unit_price_raw", sa.String(length=100), nullable=True))
        batch_op.add_column(
            sa.Column("total_amount", sa.Numeric(precision=18, scale=2), nullable=True)
        )
        batch_op.add_column(
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="CNY")
        )
        batch_op.add_column(sa.Column("source_reference", sa.String(length=255), nullable=True))
        batch_op.add_column(_updated_at_column())
        batch_op.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"))
        )

    # Backfill stable numbers before enforcing uniqueness. This also makes the
    # migration safe when a 0002 database already contains demo requirements.
    op.execute(
        "UPDATE purchase_requirement "
        "SET requirement_no = CONCAT('REQ-MIGRATED-', LPAD(id, 12, '0')) "
        "WHERE requirement_no IS NULL"
    )
    op.alter_column(
        "purchase_requirement",
        "requirement_no",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.create_unique_constraint("uk_requirement_no", "purchase_requirement", ["requirement_no"])
    op.create_unique_constraint(
        "uk_requirement_source_reference", "purchase_requirement", ["source_reference"]
    )
    op.create_index("idx_requirement_employee", "purchase_requirement", ["employee_id"])
    op.create_index("idx_requirement_status", "purchase_requirement", ["status"])
    op.create_index("idx_requirement_category", "purchase_requirement", ["category_id"])
    op.create_index("idx_requirement_product_id", "purchase_requirement", ["product_id"])
    op.create_index("idx_requirement_supplier", "purchase_requirement", ["supplier_id"])
    op.create_index("idx_requirement_previous", "purchase_requirement", ["previous_requirement_id"])
    op.create_foreign_key(
        "fk_requirement_employee",
        "purchase_requirement",
        "employee",
        ["employee_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_requirement_previous",
        "purchase_requirement",
        "purchase_requirement",
        ["previous_requirement_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_requirement_category",
        "purchase_requirement",
        "product_category",
        ["category_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_requirement_product",
        "purchase_requirement",
        "product_whitelist",
        ["product_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_requirement_supplier",
        "purchase_requirement",
        "supplier",
        ["supplier_id"],
        ["id"],
    )

    op.create_table(
        "purchase_approval",
        _id_column(),
        sa.Column("requirement_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("approver_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("approver_employee_no", sa.String(length=50), nullable=True),
        sa.Column("approver_name", sa.String(length=100), nullable=False),
        sa.Column("approver_phone", sa.String(length=50), nullable=True),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("submitted_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("acted_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        _created_at_column(),
        sa.UniqueConstraint("idempotency_key", name="uk_approval_idempotency_key"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_approval_requirement_revision",
        "purchase_approval",
        ["requirement_id", "revision_no"],
    )
    op.create_index("idx_approval_approver", "purchase_approval", ["approver_id"])
    op.create_foreign_key(
        "fk_approval_requirement",
        "purchase_approval",
        "purchase_requirement",
        ["requirement_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_approval_approver",
        "purchase_approval",
        "employee",
        ["approver_id"],
        ["id"],
    )

    with op.batch_alter_table("purchase_order") as batch_op:
        batch_op.add_column(sa.Column("supplier_name", sa.String(length=200), nullable=True))
        batch_op.add_column(
            sa.Column("unit_price", sa.Numeric(precision=18, scale=2), nullable=True)
        )
        batch_op.add_column(sa.Column("purchaser_id", mysql.BIGINT(unsigned=True), nullable=True))
        batch_op.add_column(sa.Column("purchaser_employee_no", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("purchaser_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("purchaser_phone", sa.String(length=50), nullable=True))
        batch_op.add_column(
            sa.Column("purchasing_started_at", mysql.DATETIME(fsp=6), nullable=True)
        )
        batch_op.add_column(sa.Column("quoted_at", mysql.DATETIME(fsp=6), nullable=True))
        batch_op.add_column(sa.Column("contracted_at", mysql.DATETIME(fsp=6), nullable=True))
        batch_op.add_column(sa.Column("received_at", mysql.DATETIME(fsp=6), nullable=True))
        batch_op.add_column(sa.Column("completed_at", mysql.DATETIME(fsp=6), nullable=True))
        batch_op.add_column(_updated_at_column())
        batch_op.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"))
        )
    op.create_index("idx_order_purchaser", "purchase_order", ["purchaser_id"])
    op.create_index("idx_order_status", "purchase_order", ["status"])
    op.create_foreign_key(
        "fk_order_purchaser",
        "purchase_order",
        "employee",
        ["purchaser_id"],
        ["id"],
    )

    op.create_table(
        "purchase_status_history",
        _id_column(),
        sa.Column("requirement_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("order_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("operator_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("operator_employee_no", sa.String(length=50), nullable=True),
        sa.Column("operator_name", sa.String(length=100), nullable=True),
        sa.Column("operator_phone", sa.String(length=50), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("changed_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        _created_at_column(),
        sa.CheckConstraint(
            "requirement_id IS NOT NULL OR order_id IS NOT NULL",
            name="ck_status_history_business_object",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_status_history_requirement", "purchase_status_history", ["requirement_id"])
    op.create_index("idx_status_history_order", "purchase_status_history", ["order_id"])
    op.create_index("idx_status_history_operator", "purchase_status_history", ["operator_id"])
    op.create_index("idx_status_history_changed_at", "purchase_status_history", ["changed_at"])
    op.create_foreign_key(
        "fk_status_history_requirement",
        "purchase_status_history",
        "purchase_requirement",
        ["requirement_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_status_history_order",
        "purchase_status_history",
        "purchase_order",
        ["order_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_status_history_operator",
        "purchase_status_history",
        "employee",
        ["operator_id"],
        ["id"],
    )


def downgrade() -> None:
    """Remove the approval workflow extensions without changing 0002."""
    op.drop_table("purchase_status_history")

    op.drop_constraint("fk_order_purchaser", "purchase_order", type_="foreignkey")
    op.drop_index("idx_order_status", table_name="purchase_order")
    op.drop_index("idx_order_purchaser", table_name="purchase_order")
    with op.batch_alter_table("purchase_order") as batch_op:
        batch_op.drop_column("version")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("completed_at")
        batch_op.drop_column("received_at")
        batch_op.drop_column("contracted_at")
        batch_op.drop_column("quoted_at")
        batch_op.drop_column("purchasing_started_at")
        batch_op.drop_column("purchaser_phone")
        batch_op.drop_column("purchaser_name")
        batch_op.drop_column("purchaser_employee_no")
        batch_op.drop_column("purchaser_id")
        batch_op.drop_column("unit_price")
        batch_op.drop_column("supplier_name")

    op.drop_table("purchase_approval")

    op.drop_constraint("fk_requirement_supplier", "purchase_requirement", type_="foreignkey")
    op.drop_constraint("fk_requirement_product", "purchase_requirement", type_="foreignkey")
    op.drop_constraint("fk_requirement_category", "purchase_requirement", type_="foreignkey")
    op.drop_constraint("fk_requirement_previous", "purchase_requirement", type_="foreignkey")
    op.drop_constraint("fk_requirement_employee", "purchase_requirement", type_="foreignkey")
    op.drop_index("idx_requirement_previous", table_name="purchase_requirement")
    op.drop_index("idx_requirement_supplier", table_name="purchase_requirement")
    op.drop_index("idx_requirement_product_id", table_name="purchase_requirement")
    op.drop_index("idx_requirement_category", table_name="purchase_requirement")
    op.drop_index("idx_requirement_status", table_name="purchase_requirement")
    op.drop_index("idx_requirement_employee", table_name="purchase_requirement")
    op.drop_constraint("uk_requirement_source_reference", "purchase_requirement", type_="unique")
    op.drop_constraint("uk_requirement_no", "purchase_requirement", type_="unique")
    with op.batch_alter_table("purchase_requirement") as batch_op:
        batch_op.drop_column("version")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("source_reference")
        batch_op.drop_column("currency")
        batch_op.drop_column("total_amount")
        batch_op.drop_column("unit_price_raw")
        batch_op.drop_column("unit_price")
        batch_op.drop_column("supplier_name")
        batch_op.drop_column("supplier_id")
        batch_op.drop_column("quantity_raw")
        batch_op.drop_column("product_full_name")
        batch_op.drop_column("product_id")
        batch_op.drop_column("device_type")
        batch_op.drop_column("application_location")
        batch_op.drop_column("application_reason")
        batch_op.drop_column("category_name")
        batch_op.drop_column("category_id")
        batch_op.drop_column("previous_requirement_id")
        batch_op.drop_column("revision_no")
        batch_op.drop_column("submitted_at")
        batch_op.drop_column("requested_at")
        batch_op.drop_column("applicant_phone")
        batch_op.drop_column("applicant_name")
        batch_op.drop_column("applicant_employee_no")
        batch_op.drop_column("employee_id")
        batch_op.drop_column("requirement_no")

    op.alter_column(
        "purchase_requirement",
        "quantity",
        existing_type=sa.Numeric(precision=18, scale=4),
        type_=sa.Numeric(precision=10, scale=2),
        nullable=False,
    )
    op.alter_column(
        "purchase_requirement",
        "session_id",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.alter_column(
        "product_whitelist",
        "category_id",
        existing_type=mysql.BIGINT(unsigned=True),
        nullable=False,
    )

    op.drop_table("employee")
