import json
import re
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.modules.agent.intent_recognizer import IntentCategory
from app.modules.agent.model import AgentModelProtocol


class IntentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: IntentCategory
    confidence: float = Field(ge=0, le=1)
    ambiguities: list[str] = Field(default_factory=list)


class IntentServiceProtocol(Protocol):
    async def resolve(self, message: str, history: list[dict[str, str]]) -> IntentCategory: ...


class ModelIntentService:
    def __init__(self, model: AgentModelProtocol) -> None:
        self._model = model

    async def resolve(self, message: str, history: list[dict[str, str]]) -> IntentCategory:
        response = await self._model.complete(
            system=(
                "识别员工当前意图，只返回JSON。未知事实为null，歧义写入ambiguities，不得编造。"
                "intent只能是create_requirement、supplement_requirement、modify_requirement、"
                "view_requirement、confirm_submission、cancel_requirement、query_status、"
                "list_requirements、search_historical_suppliers或unknown。"
            ),
            messages=[
                *history[-6:],
                {"role": "user", "content": message},
            ],
            tools=[],
        )
        try:
            payload: Any = json.loads(_json_object(response.text))
            decision = IntentDecision.model_validate(payload)
            if decision.confidence >= 0.5:
                return decision.intent
        except (ValueError, TypeError):
            pass
        return _fallback_intent(message)


def _json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return match.group(0) if match else "{}"


def _fallback_intent(message: str) -> IntentCategory:
    patterns = (
        (IntentCategory.CONFIRM_SUBMISSION, ("确认提交", "提交审批", "信息无误")),
        (IntentCategory.CANCEL_REQUIREMENT, ("取消采购", "取消申请", "撤销申请")),
        (
            IntentCategory.SEARCH_HISTORICAL_SUPPLIERS,
            ("历史供应商", "供应商推荐", "历史价格", "以前采购"),
        ),
        (
            IntentCategory.LIST_REQUIREMENTS,
            ("列出我的", "我的采购申请", "全部采购单", "待审批申请有哪些"),
        ),
        (IntentCategory.QUERY_STATUS, ("采购进度", "申请进度", "采购状态")),
        (IntentCategory.VIEW_REQUIREMENT, ("查看草稿", "采购草稿", "当前需求")),
        (IntentCategory.MODIFY_REQUIREMENT, ("修改", "改成", "更正", "换成")),
        (IntentCategory.SUPPLEMENT_REQUIREMENT, ("补充", "品牌是", "型号是", "供应商是")),
        (IntentCategory.CREATE_REQUIREMENT, ("采购", "购买", "申请买", "需要买")),
    )
    for intent, keywords in patterns:
        if any(keyword in message for keyword in keywords):
            return intent
    return IntentCategory.UNKNOWN
