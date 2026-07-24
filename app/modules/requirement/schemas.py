"""采购申请草稿的公共 Pydantic 数据结构。"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, field_serializer


def _decimal_string(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("必须使用十进制数字符串")
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError("必须是有效的十进制数字符串") from None


def _integer_quantity(value: Decimal) -> Decimal:
    if value != value.to_integral_value():
        raise ValueError("采购数量必须是整数")
    return value


Quantity = (
    Annotated[
        Decimal,
        BeforeValidator(_decimal_string),
        AfterValidator(_integer_quantity),
        Field(gt=0, max_digits=18, decimal_places=4),
    ]
    | None
)
Money = (
    Annotated[
        Decimal,
        BeforeValidator(_decimal_string),
        Field(ge=0, max_digits=18, decimal_places=2),
    ]
    | None
)
PositiveId = Annotated[int, Field(gt=0)]


class RequirementDraftFields(BaseModel):
    """Agent 可以逐步收集并写入草稿的字段。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: str | None = Field(default=None, max_length=100, description="来源 Agent 会话编号")
    building_id: PositiveId | None = Field(
        default=None,
        description="兼容字段；系统根据当前登录账号自动写入所属楼宇，忽略客户端传值",
    )
    category_id: PositiveId | None = Field(
        default=None, description="已匹配到的产品分类数据库 ID；不知道时留空"
    )
    category_name: (
        Literal[
            "电气",
            "暖通",
            "弱电",
            "机房环境",
            "工器具",
            "算力服务器",
            "IDC网络",
            "其他",
        ]
        | None
    ) = Field(default=None, description="兼容字段；新建申请表单无需填写，客户端传值会被忽略")
    application_reason: str | None = Field(
        default=None, max_length=5000, description="员工申请采购的原因和用途"
    )
    application_location: str | None = Field(
        default=None, max_length=200, description="设备计划使用或安装的地点"
    )
    device_type: str | None = Field(
        default=None, max_length=100, description="设备类型，例如：服务器、交换机、UPS"
    )
    product_id: PositiveId | None = Field(
        default=None, description="已匹配到的商品数据库 ID；新商品或不知道时留空"
    )
    product_name: str | None = Field(
        default=None, max_length=200, description="设备名称，例如：机架式服务器"
    )
    product_full_name: str | None = Field(
        default=None, max_length=500, description="包含品牌、型号等信息的具体设备全称"
    )
    brand: str | None = Field(default=None, max_length=100, description="设备品牌")
    model: str | None = Field(default=None, max_length=200, description="设备型号")
    specification: str | None = Field(
        default=None, max_length=5000, description="设备规格、配置和技术参数"
    )
    quantity: Quantity = Field(default=None, description="采购数量，必须用整数字符串填写，例如 2")
    unit: str | None = Field(default=None, max_length=20, description="采购单位，例如：台、个、套")
    supplier_id: PositiveId | None = Field(
        default=None, description="已匹配到的供应商数据库 ID；新供应商或未选择时留空"
    )
    supplier_name: str | None = Field(
        default=None, max_length=200, description="员工选择或填写的供应商名称"
    )
    unit_price: Money = Field(
        default=None, description="员工已知的预算或参考单价，必须用字符串填写，例如 72800.00"
    )
    currency: str = Field(default="CNY", pattern=r"^[A-Z]{3}$", description="币种，人民币填写 CNY")


class CreateRequirementDraft(RequirementDraftFields):
    """创建一张属于当前员工的采购申请草稿，允许信息不完整。"""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "session_id": None,
                    "category_id": None,
                    "category_name": "算力服务器",
                    "application_reason": "新建测试环境，需要增加服务器计算资源",
                    "application_location": "A区数据中心3楼",
                    "device_type": "服务器",
                    "product_id": None,
                    "product_name": "机架式服务器",
                    "product_full_name": "浪潮 2U双路机架式服务器",
                    "brand": "浪潮",
                    "model": "DEV-SRV-2U-DUAL",
                    "specification": "2U 双路机架服务器",
                    "quantity": "2",
                    "unit": "台",
                    "supplier_id": None,
                    "supplier_name": "员工自行选择的供应商有限公司",
                    "unit_price": "72800.00",
                    "currency": "CNY",
                }
            ]
        }
    )


class UpdateRequirementDraft(RequirementDraftFields):
    """只把本次明确提供的字段更新到已有草稿。"""

    version: int = Field(gt=0, description="上一次接口响应中的最新版本号")


class ApplicantSnapshot(BaseModel):
    employee_no: str | None
    name: str
    phone: str | None


class RequirementNotice(BaseModel):
    code: str
    message: str


class RequirementConflict(BaseModel):
    field: str
    message: str


class RequirementDetail(BaseModel):
    """返回给 Agent 和员工确认的数据库最新完整视图。"""

    requirement_id: int
    requirement_no: str
    status: str
    version: int
    applicant: ApplicantSnapshot
    session_id: str | None
    building_id: int | None = None
    category_id: int | None
    category_name: str | None
    application_reason: str | None
    application_location: str | None
    device_type: str | None
    product_id: int | None
    product_name: str | None
    product_full_name: str | None
    brand: str | None
    model: str | None
    specification: str | None
    quantity: Decimal | None
    unit: str | None
    supplier_id: int | None
    supplier_name: str | None
    unit_price: Decimal | None
    total_amount: Decimal | None
    currency: str
    new_product: bool
    new_supplier: bool
    missing_fields: list[str]
    conflicts: list[RequirementConflict]
    warnings: list[RequirementNotice]
    requested_at: datetime | None
    submitted_at: datetime | None
    updated_at: datetime

    @field_serializer("quantity")
    def serialize_quantity(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, ".0f")

    @field_serializer("unit_price", "total_amount")
    def serialize_money(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, ".2f")


class SubmitRequirement(BaseModel):
    """员工明确确认后用于进入审批流程的数据。"""

    version: int = Field(gt=0, description="采购草稿当前版本号")
    confirmed: Literal[True] = Field(description="员工是否已经人工确认；只能填写 true")
    recommendation_id: PositiveId | None = Field(
        default=None, description="员工采用的推荐记录 ID；没有采用推荐时留空"
    )


class RequirementSubmissionResult(BaseModel):
    requirement_id: int
    requirement_no: str
    status: Literal["PENDING_APPROVAL"]
    version: int
    submitted_at: datetime


class CancelRequirementDraft(BaseModel):
    """员工明确确认后用于取消草稿的数据。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    version: int = Field(gt=0, description="采购草稿当前版本号")
    confirmed: Literal[True] = Field(description="员工是否已经人工确认取消；只能填写 true")
    reason: str = Field(min_length=1, max_length=1000, description="取消采购草稿的原因")


class ReviseRejectedRequirement(BaseModel):
    """员工基于被驳回申请创建下一版本草稿。"""

    version: int = Field(gt=0, description="被驳回申请的当前版本号")
    confirmed: Literal[True] = Field(description="员工是否确认创建修改版本；只能填写 true")


class RequirementSummary(BaseModel):
    requirement_id: int
    requirement_no: str
    product_name: str | None
    status: str
    total_amount: Decimal | None
    currency: str
    updated_at: datetime
    version: int

    @field_serializer("total_amount")
    def serialize_total(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, ".2f")


class HistoricalSupplierQuery(BaseModel):
    """历史查询参数；已保存草稿始终是可信查询来源。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    requirement_id: int = Field(gt=0, description="要查询历史推荐的当前采购草稿 ID")
    product_id: PositiveId | None = None
    device_type: str | None = Field(default=None, max_length=100)
    product_name: str | None = Field(default=None, max_length=200)
    product_full_name: str | None = Field(default=None, max_length=500)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    specification: str | None = Field(default=None, max_length=5000)
    application_location: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=5, ge=1, le=20, description="最多返回多少个推荐供应商")


class HistoricalPurchaseSummary(BaseModel):
    requirement_id: int
    requirement_no: str
    order_id: int
    order_no: str
    product_name: str | None
    brand: str | None
    model: str | None
    quantity: Decimal
    unit: str | None
    unit_price: Decimal | None
    currency: str
    purchased_at: datetime | None
    received_at: datetime | None
    status: str

    @field_serializer("quantity")
    def serialize_quantity(self, value: Decimal) -> str:
        return format(value, ".4f")

    @field_serializer("unit_price")
    def serialize_unit_price(self, value: Decimal | None) -> str | None:
        return None if value is None else format(value, ".2f")


class HistoricalSupplierRecommendation(BaseModel):
    rank: int
    match_score: Decimal
    matched_fields: list[str]
    supplier_id: int | None
    supplier_name: str
    historical_order_count: int
    latest_purchase: HistoricalPurchaseSummary
    reason: str
    warnings: list[str]

    @field_serializer("match_score")
    def serialize_score(self, value: Decimal) -> str:
        return format(value, ".4f")


class HistoricalSupplierRecommendationResult(BaseModel):
    query_summary: str
    result_code: Literal["OK", "NO_HISTORY_MATCH"]
    recommendations: list[HistoricalSupplierRecommendation]
