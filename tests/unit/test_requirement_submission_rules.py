from decimal import Decimal

import pytest

from app.modules.requirement.models import PurchaseRequirement
from app.modules.requirement.service import RequirementService
from app.shared.errors import DomainError, ErrorCode
from app.shared.identity import CurrentUser


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


def test_building_is_derived_from_the_logged_in_account() -> None:
    actor = CurrentUser(user_code="E001", building_ids=frozenset({12}))

    assert RequirementService._automatic_building_id(actor) == 12


@pytest.mark.parametrize("building_ids", [frozenset(), frozenset({12, 13})])
def test_account_must_have_one_building(building_ids: frozenset[int]) -> None:
    actor = CurrentUser(user_code="E001", building_ids=building_ids)

    with pytest.raises(DomainError) as captured:
        RequirementService._automatic_building_id(actor)

    assert captured.value.code is ErrorCode.EMPLOYEE_NOT_MAPPED
