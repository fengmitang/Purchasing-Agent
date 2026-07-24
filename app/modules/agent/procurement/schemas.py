from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.agent.enums import AgentScene, AgentStage

DRAFT_FIELD_NAMES = (
    "session_id",
    "category_id",
    "category_name",
    "application_reason",
    "application_location",
    "device_type",
    "product_id",
    "product_name",
    "product_full_name",
    "brand",
    "model",
    "specification",
    "quantity",
    "unit",
    "supplier_id",
    "supplier_name",
    "unit_price",
    "currency",
)


def _decimal_string(value: Any) -> Any:
    if value is None or isinstance(value, str):
        return value


def _currency_code(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    normalized = value.strip()
    aliases = {
        "元": "CNY",
        "人民币": "CNY",
        "RMB": "CNY",
        "¥": "CNY",
        "￥": "CNY",
    }
    return aliases.get(normalized, normalized.upper())
    try:
        return str(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return value


class RequirementDraftFields(BaseModel):
    """后端 RequirementDraftInput 的 Agent 端镜像，不包含 version。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    application_reason: str | None = None
    application_location: str | None = None
    device_type: str | None = None
    product_id: int | None = None
    product_name: str | None = None
    product_full_name: str | None = None
    brand: str | None = None
    model: str | None = None
    specification: str | None = None
    quantity: str | None = None
    unit: str | None = None
    supplier_id: int | None = None
    supplier_name: str | None = None
    unit_price: str | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    _normalize_quantity = field_validator("quantity", mode="before")(_decimal_string)
    _normalize_price = field_validator("unit_price", mode="before")(_decimal_string)
    _normalize_currency = field_validator("currency", mode="before")(_currency_code)


class DraftExtraction(BaseModel):
    """LLM 只返回本轮增量变化；clear_fields 仅表示用户明确要求清空。"""

    changes: RequirementDraftFields = Field(default_factory=RequirementDraftFields)
    clear_fields: list[str] = Field(default_factory=list)

    def to_patch(self) -> dict[str, Any]:
        # LLM 输出的 null 不代表用户要求清空；清空只认 clear_fields。
        patch = {
            key: value
            for key, value in self.changes.model_dump(exclude_unset=True).items()
            if value is not None
        }
        for field_name in self.clear_fields:
            if field_name in DRAFT_FIELD_NAMES:
                patch[field_name] = None
        return patch


class RequirementDetail(BaseModel):
    model_config = ConfigDict(extra="allow")

    requirement_id: int
    requirement_no: str
    status: str
    version: int
    applicant: dict[str, Any] | None = None
    session_id: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    application_reason: str | None = None
    application_location: str | None = None
    device_type: str | None = None
    product_id: int | None = None
    product_name: str | None = None
    product_full_name: str | None = None
    brand: str | None = None
    model: str | None = None
    specification: str | None = None
    quantity: str | None = None
    unit: str | None = None
    supplier_id: int | None = None
    supplier_name: str | None = None
    unit_price: str | None = None
    total_amount: str | None = None
    currency: str = "CNY"
    new_product: bool = False
    new_supplier: bool = False
    missing_fields: list[Any] = Field(default_factory=list)
    conflicts: list[Any] = Field(default_factory=list)
    warnings: list[Any] = Field(default_factory=list)
    requested_at: str | None = None
    submitted_at: str | None = None
    updated_at: str | None = None


class RequirementSubmissionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: int
    requirement_no: str
    status: str
    version: int
    submitted_at: str


class RequirementSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    requirement_id: int
    requirement_no: str
    product_name: str | None = None
    status: str
    total_amount: str | None = None
    currency: str = "CNY"
    updated_at: str
    version: int


class RequirementListResult(BaseModel):
    items: list[RequirementSummary]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class HistoricalSupplierRecommendationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    query_summary: str
    result_code: str
    recommendations: list[dict[str, Any]] = Field(default_factory=list)


class RequirementSessionReference(BaseModel):
    requirement_id: int
    requirement_no: str
    status: str


class ProcurementSessionState(BaseModel):
    # scene/stage有默认值，因此可直接读取旧Redis JSON。
    scene: AgentScene = AgentScene.PROCUREMENT_REQUIREMENT
    stage: AgentStage = AgentStage.COLLECTING_INFORMATION
    requirement_id: int
    requirement_no: str
    version: int
    status: str
    last_recommendation_id: int | None = None
    pending_action: dict[str, Any] | None = None
    recent_requirements: list[RequirementSessionReference] = Field(default_factory=list)
    deferred_fields: list[str] = Field(default_factory=list)
