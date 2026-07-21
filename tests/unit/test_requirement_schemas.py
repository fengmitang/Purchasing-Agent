from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.requirement.schemas import CreateRequirementDraft, UpdateRequirementDraft


def test_decimal_fields_require_json_strings() -> None:
    command = CreateRequirementDraft(quantity="2", unit_price="10.20")

    assert command.quantity == Decimal("2")
    assert command.unit_price == Decimal("10.20")

    with pytest.raises(ValidationError, match="十进制数字符串"):
        CreateRequirementDraft(quantity=2.5)

    with pytest.raises(ValidationError, match="必须是整数"):
        CreateRequirementDraft(quantity="2.5")


def test_update_requires_positive_version() -> None:
    with pytest.raises(ValidationError):
        UpdateRequirementDraft(version=0, product_name="服务器")


def test_category_must_be_selected_from_the_business_list() -> None:
    assert CreateRequirementDraft(category_name="IDC网络").category_name == "IDC网络"

    with pytest.raises(ValidationError):
        CreateRequirementDraft(category_name="随意填写的类别")


def test_manual_create_schema_exposes_the_complete_editable_form() -> None:
    schema = CreateRequirementDraft.model_json_schema()

    assert {
        "category_name",
        "application_reason",
        "application_location",
        "device_type",
        "product_name",
        "product_full_name",
        "brand",
        "model",
        "specification",
        "quantity",
        "unit",
        "supplier_name",
        "unit_price",
        "currency",
    } <= schema["properties"].keys()
    assert schema["examples"][0]["product_name"] == "机架式服务器"
