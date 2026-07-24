from decimal import Decimal

from app.modules.requirement.models import PurchaseRequirement
from app.modules.requirement.service import RequirementService


def test_only_four_business_fields_are_required_for_submission() -> None:
    requirement = PurchaseRequirement(
        application_reason="机房扩容",
        application_location="A03 机房",
        product_name="机架式服务器",
        quantity=Decimal("2"),
    )

    assert RequirementService._missing_fields(requirement) == []


def test_missing_fields_only_reports_the_four_required_business_fields() -> None:
    requirement = PurchaseRequirement()

    assert RequirementService._missing_fields(requirement) == [
        "application_reason",
        "application_location",
        "product_name",
        "quantity",
    ]
