from app.modules.agent.enums import AgentScene, AgentStage
from app.modules.agent.procurement.schemas import ProcurementSessionState, RequirementDetail


def stage_for_detail(detail: RequirementDetail) -> AgentStage:
    if detail.status == "CANCELLED":
        return AgentStage.CANCELLED
    if detail.status == "COMPLETED":
        return AgentStage.COMPLETED
    if detail.status != "DRAFT":
        return AgentStage.SUBMITTED
    if detail.missing_fields or detail.conflicts:
        return AgentStage.WAITING_FOR_CLARIFICATION
    return AgentStage.WAITING_FOR_CONFIRMATION


def state_from_detail(
    detail: RequirementDetail,
    *,
    scene: AgentScene = AgentScene.PROCUREMENT_REQUIREMENT,
    previous: ProcurementSessionState | None = None,
) -> ProcurementSessionState:
    return ProcurementSessionState(
        scene=scene,
        stage=stage_for_detail(detail),
        requirement_id=detail.requirement_id,
        requirement_no=detail.requirement_no,
        version=detail.version,
        status=detail.status,
        last_recommendation_id=(previous.last_recommendation_id if previous else None),
        pending_action=(previous.pending_action if previous else None),
        recent_requirements=(list(previous.recent_requirements) if previous else []),
        deferred_fields=(list(previous.deferred_fields) if previous else []),
    )
