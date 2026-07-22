"""楼宇、楼长审批和采购执行的 HTTP 接口。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request

from app.api.dependencies import get_current_user, get_workflow_service
from app.modules.workflow.schemas import (
    AdvanceProcurement,
    ApprovalDecision,
    ApprovalDecisionResult,
    ApprovalTaskView,
    BuildingOption,
    CompleteProcurement,
    ProcurementTaskView,
    RollbackProcurement,
    StartProcurement,
)
from app.modules.workflow.service import WorkflowService
from app.shared.identity import AuditContext, CurrentUser
from app.shared.responses import PageInfo, PaginatedResponse, ResponseMeta, SuccessResponse

building_router = APIRouter(prefix="/api/v1/buildings", tags=["楼宇"])
approval_router = APIRouter(prefix="/api/v1/approvals", tags=["楼长审批"])
procurement_router = APIRouter(prefix="/api/v1/procurement", tags=["采购执行"])


def _context(request: Request, actor: CurrentUser, key: str) -> AuditContext:
    return AuditContext(
        actor=actor,
        request_id=request.state.request_id,
        idempotency_key=key,
        source_ip=request.client.host if request.client else None,
    )


@building_router.get(
    "",
    response_model=SuccessResponse[list[BuildingOption]],
    summary="查询可选择的楼宇",
    description="员工创建采购申请时使用。提交审批前必须选择所属楼宇，系统据此路由给对应楼长。",
)
async def list_buildings(
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> SuccessResponse[list[BuildingOption]]:
    del actor
    return SuccessResponse(
        data=await service.list_buildings(),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@approval_router.get(
    "/tasks",
    response_model=PaginatedResponse[ApprovalTaskView],
    summary="查询待审批任务或本人审批记录",
    description="pending 返回职责楼宇内待处理申请；history 返回当前楼长本人已经处理过的审批记录。",
)
async def list_approval_tasks(
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    view: Annotated[
        Literal["pending", "history"], Query(description="待审批或审批记录")
    ] = "pending",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[ApprovalTaskView]:
    tasks, total = await service.list_approval_tasks(
        actor, view=view, page=page, page_size=page_size
    )
    return PaginatedResponse(
        data=tasks,
        page=PageInfo(number=page, size=page_size, total=total),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@approval_router.get(
    "/tasks/{requirement_id}",
    response_model=SuccessResponse[ApprovalTaskView],
    summary="查看审批申请详情",
    description="楼长可以查看待处理申请，也可以回看本人已经处理过的申请和审批意见。",
)
async def get_approval_task(
    requirement_id: int,
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> SuccessResponse[ApprovalTaskView]:
    return SuccessResponse(
        data=await service.get_approval_task(requirement_id, actor),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@approval_router.post(
    "/tasks/{requirement_id}/decision",
    response_model=SuccessResponse[ApprovalDecisionResult],
    summary="通过或驳回采购申请",
    description="楼长只能审批职责楼宇内的申请，禁止审批本人申请；驳回时必须填写审批意见。",
)
async def decide_approval(
    requirement_id: int,
    payload: ApprovalDecision,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> SuccessResponse[ApprovalDecisionResult]:
    return SuccessResponse(
        data=await service.decide(
            requirement_id, payload, _context(request, actor, idempotency_key)
        ),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@procurement_router.get(
    "/tasks",
    response_model=PaginatedResponse[ProcurementTaskView],
    summary="查询采购员任务队列",
    description="返回审批通过、采购中以及已完成的采购任务；只有采购员角色可以访问。",
)
async def list_procurement_tasks(
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[ProcurementTaskView]:
    tasks, total = await service.list_procurement_tasks(actor, page=page, page_size=page_size)
    return PaginatedResponse(
        data=tasks,
        page=PageInfo(number=page, size=page_size, total=total),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@procurement_router.post(
    "/requirements/{requirement_id}/start",
    response_model=SuccessResponse[ProcurementTaskView],
    summary="领取任务并开始采购",
    description="采购员领取一张审批通过的申请，生成或接管采购单并记录采购人员信息和开始时间。",
)
async def start_procurement(
    requirement_id: int,
    payload: StartProcurement,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> SuccessResponse[ProcurementTaskView]:
    return SuccessResponse(
        data=await service.start_procurement(
            requirement_id, payload, _context(request, actor, idempotency_key)
        ),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@procurement_router.post(
    "/orders/{order_id}/advance",
    response_model=SuccessResponse[ProcurementTaskView],
    summary="记录询价或合同状态",
    description="按顺序记录询价核价完成和合同签订完成状态，不展开具体业务明细。",
)
async def advance_procurement(
    order_id: int,
    payload: AdvanceProcurement,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> SuccessResponse[ProcurementTaskView]:
    return SuccessResponse(
        data=await service.advance_procurement(
            order_id, payload, _context(request, actor, idempotency_key)
        ),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@procurement_router.post(
    "/orders/{order_id}/complete",
    response_model=SuccessResponse[ProcurementTaskView],
    summary="确认验收入库并完成采购",
    description="重点记录验收入库和采购完成时间，同时保存采购人员工号、姓名和联系方式快照。",
)
async def complete_procurement(
    order_id: int,
    payload: CompleteProcurement,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> SuccessResponse[ProcurementTaskView]:
    return SuccessResponse(
        data=await service.complete_procurement(
            order_id, payload, _context(request, actor, idempotency_key)
        ),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@procurement_router.post(
    "/orders/{order_id}/rollback",
    response_model=SuccessResponse[ProcurementTaskView],
    summary="撤回上一采购节点",
    description="当前采购负责人确认后，将采购单退回上一步并清除对应节点时间，操作会写入状态历史。",
)
async def rollback_procurement(
    order_id: int,
    payload: RollbackProcurement,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> SuccessResponse[ProcurementTaskView]:
    return SuccessResponse(
        data=await service.rollback_procurement(
            order_id, payload, _context(request, actor, idempotency_key)
        ),
        meta=ResponseMeta(request_id=request.state.request_id),
    )
