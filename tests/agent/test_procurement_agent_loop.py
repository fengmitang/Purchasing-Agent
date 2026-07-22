import sys
import types
import unittest

try:
    import anthropic  # noqa: F401
except ModuleNotFoundError:
    anthropic_stub = types.ModuleType("anthropic")
    anthropic_stub.AsyncAnthropic = object
    sys.modules["anthropic"] = anthropic_stub

from app.modules.agent.bootstrap import build_procurement_agent_service
from app.modules.agent.enums import AgentScene, AgentStage
from app.modules.agent.intent_recognizer import IntentCategory
from app.modules.agent.model import AgentModelResponse, AgentToolCall
from app.modules.agent.procurement.schemas import ProcurementSessionState, RequirementDetail
from app.modules.agent.procurement.session_store import InMemoryProcurementSessionStore
from app.shared.identity import CurrentUser


def draft_detail(**changes):
    base = RequirementDetail(
        requirement_id=501,
        requirement_no="PR-20260721-0501",
        status="DRAFT",
        version=1,
        applicant={"display_name": "测试用户"},
        product_name="服务器",
        quantity="2.0000",
        unit="台",
        currency="CNY",
        missing_fields=["application_reason", "application_location"],
        requested_at="2026-07-21T08:00:00+08:00",
    )
    return base.model_copy(update=changes)


def tool_decision(name, arguments, call_id="tool-1"):
    call = AgentToolCall(id=call_id, name=name, arguments=arguments)
    return AgentModelResponse(
        tool_calls=[call],
        assistant_content=[{"type": "tool_use", "id": call_id, "name": name, "input": arguments}],
    )


class QueueModel:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            return AgentModelResponse(text="没有更多操作。")
        return self.responses.pop(0)


class FakeBackend:
    def __init__(self, detail=None):
        self.detail = detail or draft_detail()
        self.create_calls = []
        self.get_calls = []
        self.update_calls = []

    async def create_draft(self, payload, **kwargs):
        self.create_calls.append((payload, kwargs))
        updates = {key: value for key, value in payload.items() if hasattr(self.detail, key)}
        self.detail = self.detail.model_copy(update=updates)
        return self.detail

    async def get_detail(self, requirement_id, **kwargs):
        self.get_calls.append((requirement_id, kwargs))
        return self.detail

    async def update_draft(self, requirement_id, payload, **kwargs):
        self.update_calls.append((requirement_id, payload, kwargs))
        updates = {key: value for key, value in payload.items() if key != "version"}
        self.detail = self.detail.model_copy(
            update={"version": self.detail.version + 1, "missing_fields": [], **updates}
        )
        return self.detail


class MultiDraftBackend(FakeBackend):
    def __init__(self, current, new_detail):
        super().__init__(current)
        self.details = {
            current.requirement_id: current,
            new_detail.requirement_id: new_detail,
        }
        self.new_detail = new_detail

    async def create_draft(self, payload, **kwargs):
        self.create_calls.append((payload, kwargs))
        updates = {key: value for key, value in payload.items() if hasattr(self.new_detail, key)}
        self.new_detail = self.new_detail.model_copy(update=updates)
        self.details[self.new_detail.requirement_id] = self.new_detail
        self.detail = self.new_detail
        return self.new_detail

    async def get_detail(self, requirement_id, **kwargs):
        self.get_calls.append((requirement_id, kwargs))
        return self.details[requirement_id]


class ProcurementAgentLoopTests(unittest.IsolatedAsyncioTestCase):
    def make_service(self, backend, model, store=None, max_iterations=6):
        store = store or InMemoryProcurementSessionStore()
        service = build_procurement_agent_service(
            backend,
            model,
            store,
            max_iterations=max_iterations,
        )
        return service, store

    async def call(
        self,
        service,
        intent,
        message="我要采购两台服务器",
        request_id="req-1",
        history=None,
    ):
        return await service.handle(
            intent=intent,
            message=message,
            user_id="employee-1",
            conv_id="session-001",
            request_id=request_id,
            actor=CurrentUser(user_code="employee-1"),
            history=history or [],
        )

    async def test_model_creates_draft_then_asks_from_tool_result(self):
        backend = FakeBackend()
        model = QueueModel(
            tool_decision(
                "create_requirement_draft",
                {"product_name": "服务器", "quantity": "2", "unit": "台"},
            ),
            AgentModelResponse(text="草稿已创建。请补充采购原因和使用地点。"),
        )
        service, store = self.make_service(backend, model)

        result = await self.call(service, IntentCategory.CREATE_REQUIREMENT)

        self.assertEqual(1, len(backend.create_calls))
        self.assertEqual("session-001", backend.create_calls[0][0]["session_id"])
        self.assertEqual("CNY", backend.create_calls[0][0]["currency"])
        self.assertEqual(501, store.get("employee-1", "session-001").requirement_id)
        self.assertEqual(AgentStage.WAITING_FOR_CLARIFICATION, result.stage)
        self.assertIn("请补充", result.response)
        event_names = [item["event"] for item in result.trace]
        self.assertIn("model.requested", event_names)
        self.assertIn("tool.completed", event_names)
        tool_result_message = model.calls[1]["messages"][-1]
        self.assertEqual("tool_result", tool_result_message["content"][0]["type"])

    async def test_model_currency_alias_is_normalized_before_create(self):
        backend = FakeBackend()
        model = QueueModel(
            tool_decision(
                "create_requirement_draft",
                {"product_name": "UPS control board", "currency": "元"},
            ),
            AgentModelResponse(text="采购草稿已创建。"),
        )
        service, _ = self.make_service(backend, model)

        await self.call(service, IntentCategory.CREATE_REQUIREMENT)

        self.assertEqual("CNY", backend.create_calls[0][0]["currency"])

    async def test_empty_create_arguments_never_reach_backend(self):
        backend = FakeBackend()
        model = QueueModel(
            tool_decision("create_requirement_draft", {}),
            AgentModelResponse(text="请先说明要采购的设备或其他采购信息。"),
        )
        service, _ = self.make_service(backend, model)
        result = await self.call(service, IntentCategory.CREATE_REQUIREMENT, "我要买点东西")
        self.assertEqual([], backend.create_calls)
        self.assertIn("请先说明", result.response)

    async def test_update_tool_gets_latest_version_and_only_sends_changes(self):
        backend = FakeBackend(draft_detail(version=7))
        store = InMemoryProcurementSessionStore()
        store.save("employee-1", "session-001", self._state(version=1))
        model = QueueModel(
            tool_decision(
                "update_requirement_draft",
                {"changes": {"application_reason": "监控平台扩容"}, "clear_fields": []},
            ),
            AgentModelResponse(text="采购原因已经更新，草稿信息已完整。"),
        )
        service, _ = self.make_service(backend, model, store)

        result = await self.call(service, IntentCategory.MODIFY_REQUIREMENT, "原因改成监控平台扩容")

        self.assertEqual(1, len(backend.get_calls))
        self.assertEqual(1, len(backend.update_calls))
        self.assertEqual(
            {"version": 7, "application_reason": "监控平台扩容"},
            backend.update_calls[0][1],
        )
        self.assertTrue(backend.update_calls[0][2]["idempotency_key"].startswith("draft-501-v7-"))
        self.assertEqual(AgentStage.WAITING_FOR_CONFIRMATION, result.stage)

    async def test_duplicate_write_in_same_turn_is_blocked(self):
        backend = FakeBackend(draft_detail(version=3))
        store = InMemoryProcurementSessionStore()
        store.save("employee-1", "session-001", self._state(version=3))
        arguments = {"changes": {"quantity": "3"}, "clear_fields": []}
        calls = [
            AgentToolCall(id="write-1", name="update_requirement_draft", arguments=arguments),
            AgentToolCall(id="write-2", name="update_requirement_draft", arguments=arguments),
        ]
        model = QueueModel(
            AgentModelResponse(
                tool_calls=calls,
                assistant_content=[
                    {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
                    for call in calls
                ],
            ),
            AgentModelResponse(text="数量已修改为3台。"),
        )
        service, _ = self.make_service(backend, model, store)
        await self.call(service, IntentCategory.MODIFY_REQUIREMENT, "数量改成3台")
        self.assertEqual(1, len(backend.update_calls))
        results = model.calls[1]["messages"][-1]["content"]
        self.assertIn("DUPLICATE_WRITE_BLOCKED", results[1]["content"])

    async def test_unregistered_tool_is_returned_to_model_without_execution(self):
        backend = FakeBackend()
        model = QueueModel(
            tool_decision("execute_sql", {"sql": "DELETE FROM x"}),
            AgentModelResponse(text="当前没有可执行的数据库操作。"),
        )
        service, _ = self.make_service(backend, model)
        result = await self.call(service, IntentCategory.CREATE_REQUIREMENT)
        self.assertEqual([], backend.create_calls)
        self.assertIn("没有可执行", result.response)
        self.assertIn("TOOL_NOT_ALLOWED", model.calls[1]["messages"][-1]["content"][0]["content"])

    async def test_confirmation_only_gets_detail_and_cannot_claim_submission(self):
        backend = FakeBackend(draft_detail(missing_fields=[], conflicts=[]))
        store = InMemoryProcurementSessionStore()
        store.save("employee-1", "session-001", self._state())
        model = QueueModel(
            tool_decision("get_requirement_detail", {}),
            AgentModelResponse(text="采购需求已成功提交。"),
        )
        service, _ = self.make_service(backend, model, store)

        result = await self.call(service, IntentCategory.CONFIRM_SUBMISSION, "确认提交")

        self.assertEqual(1, len(backend.get_calls))
        self.assertEqual([], backend.update_calls)
        self.assertNotIn("成功提交", result.response)
        self.assertIn("尚未正式提交", result.response)
        available = {item["name"] for item in model.calls[0]["tools"]}
        self.assertEqual({"get_requirement_detail"}, available)

    async def test_cancellation_cannot_claim_an_unsupported_state_change(self):
        backend = FakeBackend(draft_detail())
        store = InMemoryProcurementSessionStore()
        store.save("employee-1", "session-001", self._state())
        model = QueueModel(AgentModelResponse(text="采购需求已经取消。"))
        service, _ = self.make_service(backend, model, store)

        result = await self.call(service, IntentCategory.CANCEL_REQUIREMENT, "取消采购")

        self.assertNotIn("已经取消", result.response)
        self.assertIn("没有执行取消", result.response)
        available = {item["name"] for item in model.calls[0]["tools"]}
        self.assertEqual({"get_requirement_detail"}, available)

    async def test_agent_stops_at_iteration_limit(self):
        backend = FakeBackend()
        store = InMemoryProcurementSessionStore()
        store.save("employee-1", "session-001", self._state())
        model = QueueModel(
            tool_decision("get_requirement_detail", {}, "read-1"),
            tool_decision("get_requirement_detail", {}, "read-2"),
        )
        service, _ = self.make_service(backend, model, store, max_iterations=2)
        result = await self.call(service, IntentCategory.VIEW_REQUIREMENT, "查看草稿")
        self.assertIn("最大工具调用次数", result.response)
        self.assertEqual("agent.limit_reached", result.trace[-1]["event"])

    async def test_unknown_short_answer_with_session_becomes_supplement(self):
        backend = FakeBackend()
        store = InMemoryProcurementSessionStore()
        store.save("employee-1", "session-001", self._state())
        model = QueueModel(AgentModelResponse(text="已理解你补充的是使用地点，请确认具体机房。"))
        service, _ = self.make_service(backend, model, store)
        result = await self.call(service, IntentCategory.UNKNOWN, "2号楼")
        self.assertEqual(IntentCategory.SUPPLEMENT_REQUIREMENT, result.intent)

    async def test_general_query_exposes_no_tools(self):
        backend = FakeBackend()
        model = QueueModel(AgentModelResponse(text="你好，我可以帮你整理问题。"))
        service, _ = self.make_service(backend, model)

        result = await self.call(service, IntentCategory.UNKNOWN, "你好")

        self.assertEqual(AgentScene.GENERAL_QUERY, result.scene)
        self.assertEqual([], model.calls[0]["tools"])
        self.assertEqual([], backend.create_calls)

    async def test_same_conversation_can_start_new_draft_and_switch_back(self):
        old_detail = draft_detail(
            requirement_id=501,
            requirement_no="MOCK-PR-1006",
            product_name="集中旁路控制板",
            missing_fields=[],
        )
        new_detail = draft_detail(
            requirement_id=502,
            requirement_no="MOCK-PR-1007",
            product_name="冷却塔电机轴承",
            model="NU 213E C3",
            quantity="4",
            unit="个",
            missing_fields=["supplier_name"],
        )
        backend = MultiDraftBackend(old_detail, new_detail)
        store = InMemoryProcurementSessionStore()
        store.save(
            "employee-1",
            "session-001",
            ProcurementSessionState(
                requirement_id=501,
                requirement_no="MOCK-PR-1006",
                version=1,
                status="DRAFT",
            ),
        )
        model = QueueModel(
            tool_decision(
                "start_new_requirement",
                {
                    "application_location": "4号楼",
                    "device_type": "冷却塔电机轴承",
                    "product_name": "冷却塔电机轴承",
                    "brand": "NSK",
                    "model": "NU 213E C3",
                    "quantity": "4",
                    "unit": "个",
                    "unit_price": "430",
                },
                "new-1",
            ),
            AgentModelResponse(text="新草稿已创建，原草稿已保留。"),
            tool_decision("switch_active_requirement", {"requirement_id": 501}, "switch-1"),
            AgentModelResponse(text="已切回集中旁路控制板草稿。"),
        )
        service, _ = self.make_service(backend, model, store)

        first = await self.call(
            service,
            IntentCategory.CREATE_REQUIREMENT,
            "这是另一个需求：4号楼采购4个冷却塔电机轴承",
        )
        first_state = store.get("employee-1", "session-001")
        self.assertEqual(502, first_state.requirement_id)
        self.assertEqual([501], [item.requirement_id for item in first_state.recent_requirements])
        self.assertEqual(1, len(backend.create_calls))
        self.assertIn("原草稿已保留", first.response)
        first_tools = {item["name"] for item in model.calls[0]["tools"]}
        self.assertIn("start_new_requirement", first_tools)

        second = await self.call(
            service,
            IntentCategory.UNKNOWN,
            "切回MOCK-PR-1006",
            request_id="req-switch",
        )
        second_state = store.get("employee-1", "session-001")
        self.assertEqual(501, second_state.requirement_id)
        self.assertEqual([502], [item.requirement_id for item in second_state.recent_requirements])
        self.assertIn("已切回", second.response)
        self.assertEqual(501, backend.get_calls[-1][0])

    def test_unknown_without_procurement_context_stays_outside_agent(self):
        backend = FakeBackend()
        service, _ = self.make_service(backend, QueueModel())
        self.assertFalse(
            service.should_handle(
                IntentCategory.UNKNOWN,
                "employee-1",
                "session-001",
                history=[{"role": "user", "content": "你好"}],
            )
        )

    def test_old_redis_state_is_compatible(self):
        state = ProcurementSessionState.model_validate(
            {
                "requirement_id": 501,
                "requirement_no": "PR-20260721-0501",
                "version": 1,
                "status": "DRAFT",
            }
        )
        self.assertEqual(AgentScene.PROCUREMENT_REQUIREMENT, state.scene)
        self.assertEqual(AgentStage.COLLECTING_INFORMATION, state.stage)
        self.assertEqual([], state.recent_requirements)

    @staticmethod
    def _state(version=1):
        return ProcurementSessionState(
            requirement_id=501,
            requirement_no="PR-20260721-0501",
            version=version,
            status="DRAFT",
        )


if __name__ == "__main__":
    unittest.main()
