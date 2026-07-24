from app.modules.agent.context import AgentContext
from app.modules.agent.enums import AgentScene, AgentStage, IntentCategory
from app.modules.agent.procurement.schemas import ProcurementSessionState
from app.modules.agent.procurement.session_store import ProcurementSessionStoreProtocol
from app.modules.agent.result import AgentHandleResult
from app.modules.agent.routes import AgentRoute, RouteDecision, RouteResolver
from app.modules.agent.runner import AgentLoopRuntime
from app.shared.identity import CurrentUser


class AgentService:
    def __init__(
        self,
        runner: AgentLoopRuntime,
        session_store: ProcurementSessionStoreProtocol,
        route_resolver: RouteResolver | None = None,
    ) -> None:
        self._runner = runner
        self._session_store = session_store
        self._route_resolver = route_resolver or RouteResolver()

    async def has_session(self, organization_id: int, user_id: str, conv_id: str) -> bool:
        return await self._session_store.get(organization_id, user_id, conv_id) is not None

    async def get_session_state(
        self, organization_id: int, user_id: str, conv_id: str
    ) -> ProcurementSessionState | None:
        return await self._session_store.get(organization_id, user_id, conv_id)

    async def save_session_state(
        self,
        organization_id: int,
        user_id: str,
        conv_id: str,
        state: ProcurementSessionState,
    ) -> None:
        await self._session_store.save(organization_id, user_id, conv_id, state)

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
        active_route: AgentRoute | None = None,
        route_decision: RouteDecision | None = None,
    ) -> AgentHandleResult:
        state = state_override or await self._session_store.get(
            actor.organization_id, user_id, conv_id
        )
        decision = route_decision or self._route_resolver.resolve(
            message=message,
            intent=intent,
            has_procurement_state=state is not None,
            active_route=active_route,
            history=history,
        )
        effective_intent = self._route_resolver.effective_intent(
            intent, has_procurement_state=state is not None, history=history
        )

        scene = self._scene_for(effective_intent, decision.route)
        route = decision.route
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
            route=route,
            route_needs_clarification=decision.needs_clarification,
        )

        result = await self._runner.run(context)
        if result.procurement_state is not None and persist_state:
            result.procurement_state.scene = result.scene
            result.procurement_state.stage = result.stage
            await self._session_store.save(
                actor.organization_id,
                user_id,
                conv_id,
                result.procurement_state,
            )
        return result

    async def clear_session_state(self, organization_id: int, user_id: str, conv_id: str) -> None:
        await self._session_store.clear(organization_id, user_id, conv_id)

    @staticmethod
    def _scene_for(intent: IntentCategory, route: AgentRoute) -> AgentScene:
        if route == AgentRoute.GENERAL:
            return AgentScene.GENERAL_QUERY
        if intent == IntentCategory.QUERY_STATUS:
            return AgentScene.PROCUREMENT_STATUS
        return AgentScene.PROCUREMENT_REQUIREMENT
