import pytest
from pydantic import ValidationError

from app.modules.agent.procurement.schemas import RequirementDraftFields


@pytest.mark.parametrize("value", ["元", "人民币", "RMB", "¥", "￥", "cny"])
def test_currency_aliases_are_normalized_to_cny(value: str) -> None:
    fields = RequirementDraftFields(currency=value)

    assert fields.currency == "CNY"


def test_invalid_currency_is_rejected_by_agent_tool_schema() -> None:
    with pytest.raises(ValidationError):
        RequirementDraftFields(currency="人民币元")
