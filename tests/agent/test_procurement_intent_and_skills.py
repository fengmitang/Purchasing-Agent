import sys
import types
import unittest
from pathlib import Path

try:
    import anthropic  # noqa: F401
except ModuleNotFoundError:
    anthropic_stub = types.ModuleType("anthropic")

    class AsyncAnthropic:  # pragma: no cover - 仅用于无依赖的规则单测
        pass

    anthropic_stub.AsyncAnthropic = AsyncAnthropic
    sys.modules["anthropic"] = anthropic_stub

try:
    import httpx  # noqa: F401
except ModuleNotFoundError:
    httpx_stub = types.ModuleType("httpx")
    httpx_stub.HTTPError = Exception

    class AsyncClient:  # pragma: no cover - 流程单测使用假后端
        pass

    httpx_stub.AsyncClient = AsyncClient
    sys.modules["httpx"] = httpx_stub

from app.modules.agent.intent_recognizer import IntentCategory, IntentRecognizer
from app.modules.agent.skill_loader import SkillManager


class ProcurementIntentRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        # 规则识别不依赖网络客户端，避免单元测试调用真实模型。
        self.recognizer = object.__new__(IntentRecognizer)

    def test_procurement_intents(self) -> None:
        cases = {
            "我要给3号楼采购两个UPS功率模块": IntentCategory.CREATE_REQUIREMENT,
            "买两台服务器": IntentCategory.CREATE_REQUIREMENT,
            "补充一下，品牌是科士达": IntentCategory.SUPPLEMENT_REQUIREMENT,
            "数量改成3台": IntentCategory.MODIFY_REQUIREMENT,
            "查看当前采购草稿": IntentCategory.VIEW_REQUIREMENT,
            "信息无误，确认提交审批": IntentCategory.CONFIRM_SUBMISSION,
            "这个采购需求不要了": IntentCategory.CANCEL_REQUIREMENT,
            "我的采购申请审批到哪了": IntentCategory.QUERY_STATUS,
            "你好": IntentCategory.UNKNOWN,
        }

        for message, expected in cases.items():
            with self.subTest(message=message):
                actual = self.recognizer._pattern_recognize(message)["intent"]
                self.assertEqual(expected, actual)

    def test_strong_action_takes_priority_over_procurement_word(self) -> None:
        result = self.recognizer._pattern_recognize("取消采购申请，不要了")
        self.assertEqual(IntentCategory.CANCEL_REQUIREMENT, result["intent"])

    def test_cache_key_contains_recent_context(self) -> None:
        first = self.recognizer._cache_key(
            "科士达",
            [{"role": "assistant", "content": "请补充品牌"}],
        )
        second = self.recognizer._cache_key(
            "科士达",
            [{"role": "assistant", "content": "请选择供应商"}],
        )
        self.assertNotEqual(first, second)


class ProcurementIntentFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_llm_failure_falls_back_to_procurement_rule(self) -> None:
        recognizer = object.__new__(IntentRecognizer)
        recognizer._embedding_enabled = False
        recognizer._cache = {}
        recognizer.cache_hits = 0
        recognizer.cache_misses = 0
        recognizer.threshold = 0.5

        async def failed_llm(message, history):
            return {
                "intent": IntentCategory.UNKNOWN,
                "confidence": 0.0,
                "reasoning": "test failure",
                "failed": True,
            }

        async def no_entities(message):
            return {}

        recognizer._llm_recognize = failed_llm
        recognizer._extract_entities = no_entities

        result = await recognizer.recognize("信息无误，确认提交审批")

        self.assertEqual(IntentCategory.CONFIRM_SUBMISSION, result.intent)
        self.assertGreaterEqual(result.confidence, 0.7)


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

    def test_history_message_injects_recommendation_skill(self) -> None:
        prompt = self.manager.prompt_for("查询这个型号的历史价格", "general")
        self.assertIn("recommend-historical-supplier", prompt)

    def test_confirmation_message_injects_confirmation_skill(self) -> None:
        prompt = self.manager.prompt_for("信息无误，确认提交审批", "general")
        self.assertIn("confirm-procurement-requirement", prompt)


if __name__ == "__main__":
    unittest.main()
