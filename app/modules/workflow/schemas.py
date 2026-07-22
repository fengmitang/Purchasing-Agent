"""审批任务、采购任务和楼宇选项的公共接口结构。"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class BuildingOption(BaseModel):
    """员工创建采购申请时可选择的有效楼宇。"""

    building_id: int
    building_code: str
    building_name: str


class WorkflowApplicant(BaseModel):
    employee_id: int | None
    employee_no: str | None
    name: str
    phone: str | None


class ApprovalTaskView(BaseModel):
    """楼长列表和详情页使用的完整申请快照。"""

    requirement_id: int
    requirement_no: str
    status: str
    version: int
    revision_no: int
    building_id: int
    building_name: str
    applicant: WorkflowApplicant
    category_name: str | None
    application_reason: str | None
    application_location: str | None
    device_type: str | None
    product_name: str | None
    product_full_name: str | None
    brand: str | None
    model: str | None
    specification: str | None
    quantity: Decimal | None
    unit: str | None
    supplier_name: str | None
    unit_price: Decimal | None
    total_amount: Decimal | None
    currency: str
    submitted_at: datetime | None
    updated_at: datetime
    approval_action: str | None = None
    approval_comment: str | None = None
    approver_employee_no: str | None = None
    approver_name: str | None = None
    approver_phone: str | None = None
    acted_at: datetime | None = None

    @field_serializer("quantity")
    def serialize_quantity(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, ".0f")

    @field_serializer("unit_price", "total_amount")
    def serialize_money(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, ".2f")


class ApprovalDecision(BaseModel):
    """楼长对待审批申请作出的明确决定。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    version: int = Field(gt=0, description="审批页面读取到的申请版本号")
    action: Literal["APPROVED", "REJECTED"] = Field(description="通过或驳回")
    comment: str | None = Field(default=None, max_length=2000, description="审批意见")


class ApprovalDecisionResult(BaseModel):
    requirement_id: int
    requirement_no: str
    status: Literal["APPROVED", "REJECTED"]
    version: int
    acted_at: datetime


class ProcurementTaskView(BaseModel):
    """采购员队列中的申请、采购单和关键时间。"""

    requirement_id: int
    requirement_no: str
    status: str
    requirement_version: int
    building_id: int | None
    building_name: str | None
    applicant_name: str
    applicant_employee_no: str | None = None
    applicant_phone: str | None = None
    approver_employee_no: str | None = None
    approver_name: str | None = None
    approver_phone: str | None = None
    approval_comment: str | None = None
    approved_at: datetime | None = None
    product_name: str | None
    product_full_name: str | None
    brand: str | None
    model: str | None
    specification: str | None
    quantity: Decimal | None
    unit: str | None
    supplier_name: str | None
    unit_price: Decimal | None
    total_amount: Decimal | None
    currency: str
    order_id: int | None
    order_no: str | None
    order_version: int | None
    purchaser_employee_no: str | None
    purchaser_name: str | None
    purchaser_phone: str | None
    purchasing_started_at: datetime | None
    quoted_at: datetime | None
    contracted_at: datetime | None
    received_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    @field_serializer("quantity")
    def serialize_quantity(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, ".0f")

    @field_serializer("unit_price", "total_amount")
    def serialize_money(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, ".2f")


class StartProcurement(BaseModel):
    version: int = Field(gt=0, description="审批通过申请的当前版本号")


class AdvanceProcurement(BaseModel):
    version: int = Field(gt=0, description="采购单当前版本号")
    target_status: Literal["QUOTED", "CONTRACTED"] = Field(description="要记录的采购节点")
    remark: str | None = Field(default=None, max_length=1000, description="节点说明")


class CompleteProcurement(BaseModel):
    version: int = Field(gt=0, description="采购单当前版本号")
    remark: str | None = Field(default=None, max_length=1000, description="验收入库说明")


class RollbackProcurement(BaseModel):
    """采购员撤回刚完成的业务节点。"""

    version: int = Field(gt=0, description="采购单当前版本号")
