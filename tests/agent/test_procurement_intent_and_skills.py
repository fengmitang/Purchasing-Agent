import unittest
from pathlib import Path

from app.modules.agent.enums import IntentCategory
from app.modules.agent.intent_service import (
    ModelProcurementIntentResolver,
    _fallback_intent,
)
from app.modules.agent.model import AgentModelResponse
from app.modules.agent.skill_loader import SkillManager


class StubModel:
    def __init__(self, text: str) -> None:
        self._text = text

    async def complete(self, **kwargs) -> AgentModelResponse:
        return AgentModelResponse(text=self._text)


class ProcurementIntentRuleTests(unittest.TestCase):
    def test_procurement_intents(self) -> None:
        cases = {
            "我要给3号楼采购两个UPS功率模块": IntentCategory.CREATE_REQUIREMENT,
            "买两台服务器": IntentCategory.CREATE_REQUIREMENT,
            "补充一下，品牌是科士达": IntentCategory.SUPPLEMENT_REQUIREMENT,
            "数量改成3台": IntentCategory.MODIFY_REQUIREMENT,
            "查看当前采购草稿": IntentCategory.VIEW_REQUIREMENT,
            "信息无误，确认提交审批": IntentCategory.CONFIRM_SUBMISSION,
            "取消采购申请，不要了": IntentCategory.CANCEL_REQUIREMENT,
            "我的采购状态": IntentCategory.QUERY_STATUS,
            "列出我的采购申请": IntentCategory.LIST_REQUIREMENTS,
            "推荐这个草稿的历史供应商": IntentCategory.SEARCH_HISTORICAL_SUPPLIERS,
            "你好": IntentCategory.UNKNOWN,
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(expected, _fallback_intent(message))


class ProcurementIntentResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_model_result_is_used(self) -> None:
        resolver = ModelProcurementIntentResolver(
            StubModel('{"intent":"confirm_submission","confidence":0.9}')
        )
        result = await resolver.resolve("确认提交", [])
        self.assertEqual(IntentCategory.CONFIRM_SUBMISSION, result)

    async def test_invalid_model_result_falls_back_to_rules(self) -> None:
        resolver = ModelProcurementIntentResolver(StubModel("not-json"))
        result = await resolver.resolve("信息无误，确认提交审批", [])
        self.assertEqual(IntentCategory.CONFIRM_SUBMISSION, result)

    async def test_mixed_history_and_whitelist_request_keeps_history_search_intent(self) -> None:
        resolver = ModelProcurementIntentResolver(
            StubModel('{"intent":"unknown","confidence":0.99}')
        )
        result = await resolver.resolve(
            "搜索历史采购白名单，推荐科士达功率模块的历史采购记录和供应商白名单",
            [],
        )
        self.assertEqual(IntentCategory.SEARCH_HISTORICAL_SUPPLIERS, result)


class ProcurementSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skills_dir = Path(__file__).resolve().parents[2] / "skills"
        cls.manager = SkillManager(str(cls.skills_dir))
        cls.manager.load()

    def test_three_procurement_skills_are_loaded(self) -> None:
        loaded = {skill.name for skill in self.manager.skills}
        self.assertTrue(
            {
                "collect-procurement-requirement",
                "recommend-historical-supplier",
                "confirm-procurement-requirement",
            }.issubset(loaded)
        )
        self.assertEqual([], self.manager.errors)

    def test_requirement_message_injects_collection_skill(self) -> None:
        prompt = self.manager.prompt_for("我要采购两台服务器", "general")
        self.assertIn("collect-procurement-requirement", prompt)
        self.assertIn("提交审批必填字段", prompt)
        self.assertIn("禁止通过检查其他字段是否为 `null` 自行推断缺失信息", prompt)
        self.assertIn("最多两个；没有缺失字段时不得追问", prompt)

    def test_history_message_injects_recommendation_skill(self) -> None:
        prompt = self.manager.prompt_for("查询这个型号的历史价格", "general")
        self.assertIn("recommend-historical-supplier", prompt)

    def test_confirmation_message_injects_confirmation_skill(self) -> None:
        prompt = self.manager.prompt_for("信息无误，确认提交审批", "general")
        self.assertIn("confirm-procurement-requirement", prompt)


if __name__ == "__main__":
    unittest.main()
