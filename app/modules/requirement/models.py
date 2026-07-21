"""采购申请草稿及关联记录的 SQLAlchemy 映射。"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class Employee(Base):
    """用于归属和操作采购申请的员工身份。"""

    __tablename__ = "employee"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_no: Mapped[str | None] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(50))
    role: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)


class ProductCategory(Base):
    """用于校验草稿可选关联的产品类别。"""

    __tablename__ = "product_category"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class Product(Base):
    """用于填充确认草稿快照的白名单产品。"""

    __tablename__ = "product_whitelist"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    category_id: Mapped[int | None] = mapped_column(BigInteger)
    product_name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(200))
    specification: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str | None] = mapped_column(String(20))


class Supplier(Base):
    """用于填充可选供应商快照的供应商主数据。"""

    __tablename__ = "supplier"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    supplier_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str | None] = mapped_column(String(20))


class PurchaseRequirement(Base):
    """员工所属且可编辑的采购申请草稿。"""

    __tablename__ = "purchase_requirement"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String(100))
    product_name: Mapped[str | None] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(200))
    specification: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    requirement_no: Mapped[str] = mapped_column(String(100), unique=True)
    employee_id: Mapped[int | None] = mapped_column(BigInteger)
    applicant_employee_no: Mapped[str | None] = mapped_column(String(50))
    applicant_name: Mapped[str | None] = mapped_column(String(100))
    applicant_phone: Mapped[str | None] = mapped_column(String(50))
    requested_at: Mapped[datetime | None] = mapped_column(DateTime)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    revision_no: Mapped[int] = mapped_column(Integer)
    previous_requirement_id: Mapped[int | None] = mapped_column(BigInteger)
    category_id: Mapped[int | None] = mapped_column(BigInteger)
    category_name: Mapped[str | None] = mapped_column(String(100))
    application_reason: Mapped[str | None] = mapped_column(Text)
    application_location: Mapped[str | None] = mapped_column(String(200))
    device_type: Mapped[str | None] = mapped_column(String(100))
    product_id: Mapped[int | None] = mapped_column(BigInteger)
    product_full_name: Mapped[str | None] = mapped_column(String(500))
    quantity_raw: Mapped[str | None] = mapped_column(String(100))
    supplier_id: Mapped[int | None] = mapped_column(BigInteger)
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    unit_price_raw: Mapped[str | None] = mapped_column(String(100))
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    source_reference: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer)


class IdempotencyRecord(Base):
    """用于安全重放写请求的持久化响应快照。"""

    __tablename__ = "idempotency_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_code: Mapped[str] = mapped_column(String(50))
    operation: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[int | None] = mapped_column(BigInteger)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class PurchaseOrder(Base):
    """历史供应商推荐使用的已完成采购事实。"""

    __tablename__ = "purchase_order"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(100))
    requirement_id: Mapped[int] = mapped_column(BigInteger)
    product_id: Mapped[int] = mapped_column(BigInteger)
    supplier_id: Mapped[int | None] = mapped_column(BigInteger)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    received_at: Mapped[datetime | None] = mapped_column(DateTime)


class Recommendation(Base):
    """提交时可选择引用的已保存推荐记录。"""

    __tablename__ = "recommendation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    requirement_id: Mapped[int] = mapped_column(BigInteger)
    product_id: Mapped[int] = mapped_column(BigInteger)
    supplier_id: Mapped[int | None] = mapped_column(BigInteger)
    selected: Mapped[bool | None]


class PurchaseStatusHistory(Base):
    """采购申请和订单只追加不覆盖的状态变更历史。"""

    __tablename__ = "purchase_status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    requirement_id: Mapped[int | None] = mapped_column(BigInteger)
    order_id: Mapped[int | None] = mapped_column(BigInteger)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    operator_id: Mapped[int | None] = mapped_column(BigInteger)
    operator_employee_no: Mapped[str | None] = mapped_column(String(50))
    operator_name: Mapped[str | None] = mapped_column(String(100))
    operator_phone: Mapped[str | None] = mapped_column(String(50))
    remark: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime)
    request_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime)
