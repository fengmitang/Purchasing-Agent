from app.modules.agent.context import AgentContext
from app.modules.agent.enums import AgentScene, AgentStage
from app.modules.agent.intent_recognizer import IntentCategory
from app.modules.agent.procurement.schemas import ProcurementSessionState
from app.modules.agent.procurement.session_store import ProcurementSessionStoreProtocol
from app.modules.agent.result import AgentHandleResult
from app.modules.agent.runner import ProcurementAgentRunner
from app.shared.identity import CurrentUser


class AgentService:
    HANDLED_INTENTS = {
        IntentCategory.CREATE_REQUIREMENT,
        IntentCategory.SUPPLEMENT_REQUIREMENT,
        IntentCategory.MODIFY_REQUIREMENT,
        IntentCategory.VIEW_REQUIREMENT,
        IntentCategory.CONFIRM_SUBMISSION,
        IntentCategory.QUERY_STATUS,
    }

    def __init__(
        self,
        runner: ProcurementAgentRunner,
        session_store: ProcurementSessionStoreProtocol,
    ) -> None:
        self._runner = runner
        self._session_store = session_store

    def has_session(self, user_id: str, conv_id: str) -> bool:
        return self._session_store.get(user_id, conv_id) is not None

    def should_handle(
        self,
        intent: IntentCategory,
        user_id: str,
        conv_id: str,
        history: list[dict[str, str]] | None = None,
    ) -> bool:
        return intent in self.HANDLED_INTENTS or (
            intent == IntentCategory.UNKNOWN
            and (
                self.has_session(user_id, conv_id)
                or self._history_has_procurement_context(history or [])
            )
        )

    async def handle(
        self,
        *,
        intent: IntentCategory,
        message: str,
        user_id: str,
        conv_id: str,
        request_id: str,
        actor: CurrentUser,
        history: list[dict[str, str]] | None = None,
        state_override: ProcurementSessionState | None = None,
        persist_state: bool = True,
    ) -> AgentHandleResult:
        state = state_override or self._session_store.get(user_id, conv_id)
        effective_intent = intent
        if intent == IntentCategory.UNKNOWN and state is not None:
            effective_intent = IntentCategory.SUPPLEMENT_REQUIREMENT
        elif intent == IntentCategory.UNKNOWN and self._history_has_procurement_context(
            history or []
        ):
            effective_intent = IntentCategory.CREATE_REQUIREMENT

        scene = self._scene_for(effective_intent)
        stage = (
            state.stage
            if state is not None
            else (
                AgentStage.INTENT_RECOGNITION
                if scene == AgentScene.GENERAL_QUERY
                else AgentStage.COLLECTING_INFORMATION
            )
        )
        context = AgentContext(
            request_id=request_id,
            user_id=user_id,
            conv_id=conv_id,
            message=message,
            actor=actor,
            history=history or [],
            intent=effective_intent,
            scene=scene,
            stage=stage,
            procurement_state=state,
        )

        result = await self._runner.run(context)
        if result.procurement_state is not None and persist_state:
            result.procurement_state.scene = result.scene
            result.procurement_state.stage = result.stage
            self._session_store.save(user_id, conv_id, result.procurement_state)
        return result

    @staticmethod
    def _scene_for(intent: IntentCategory) -> AgentScene:
        if intent == IntentCategory.QUERY_STATUS:
            return AgentScene.PROCUREMENT_STATUS
        if intent == IntentCategory.UNKNOWN:
            return AgentScene.GENERAL_QUERY
        return AgentScene.PROCUREMENT_REQUIREMENT

    @staticmethod
    def _history_has_procurement_context(history: list[dict[str, str]]) -> bool:
        markers = (
            "采购草稿",
            "采购需求",
            "要采购的设备",
            "请补充采购",
            "确认提交",
        )
        return any(
            any(marker in str(item.get("content", "")) for marker in markers)
            for item in history[-6:]
        )
