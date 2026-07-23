"""采购申请草稿操作的 HTTP 接口适配层。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, status

from app.api.dependencies import get_current_user, get_requirement_service
from app.modules.requirement.schemas import (
    CancelRequirementDraft,
    CreateRequirementDraft,
    HistoricalSupplierQuery,
    HistoricalSupplierRecommendationResult,
    RequirementDetail,
    RequirementSubmissionResult,
    RequirementSummary,
    ReviseRejectedRequirement,
    SubmitRequirement,
    UpdateRequirementDraft,
)
from app.modules.requirement.service import RequirementService
from app.shared.errors import DomainError, ErrorCode
from app.shared.identity import AuditContext, CurrentUser
from app.shared.responses import PageInfo, PaginatedResponse, ResponseMeta, SuccessResponse

router = APIRouter(prefix="/api/v1/purchase-requirements", tags=["采购申请"])
recommendation_router = APIRouter(prefix="/api/v1/recommendations", tags=["采购推荐"])


def _audit_context(
    request: Request,
    actor: CurrentUser,
    idempotency_key: str,
) -> AuditContext:
    client_host = request.client.host if request.client else None
    return AuditContext(
        actor=actor,
        request_id=request.state.request_id,
        idempotency_key=idempotency_key,
        source_ip=client_host,
    )


@router.post(
    "/drafts",
    response_model=SuccessResponse[RequirementDetail],
    status_code=status.HTTP_201_CREATED,
    summary="创建采购申请草稿（支持手工表单或 Agent 辅助）",
    description=(
        "这是人工填表和 Agent 对话共用的创建入口。没有 Agent 时，员工可以一次填写完整表单；"
        "使用 Agent 时，也可以先提交已识别的部分字段，系统通过 `missing_fields` 告知还缺什么，"
        "随后再调用修改草稿接口逐步补齐。`session_id` 只用于关联 Agent 会话，人工填表时留空。"
        "申请人姓名、电话和所属楼宇从当前登录员工自动取得，申请时间由系统记录，"
        "总价由数量乘单价自动计算，"
        "这些字段不能由用户伪造。需要填写 `X-User-Code` 和唯一的 `Idempotency-Key`。"
        "此接口只保存草稿，不会自动提交审批。"
    ),
)
async def create_requirement_draft(
    payload: CreateRequirementDraft,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[RequirementService, Depends(get_requirement_service)],
) -> SuccessResponse[RequirementDetail]:
    detail = await service.create_draft(payload, _audit_context(request, actor, idempotency_key))
    return SuccessResponse(
        data=detail,
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@router.get(
    "",
    response_model=PaginatedResponse[RequirementSummary],
    summary="查询当前员工的采购申请列表",
    description=(
        "分页查看当前登录员工自己的采购申请，可按状态筛选。`mine` 必须为 true；"
        "`page` 是页码，`page_size` 是每页数量，最大 100。"
    ),
)
async def list_my_requirements(
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[RequirementService, Depends(get_requirement_service)],
    mine: Annotated[bool, Query()] = True,
    requirement_status: Annotated[str | None, Query(alias="status", max_length=30)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[RequirementSummary]:
    if not mine:
        raise DomainError(ErrorCode.FORBIDDEN, "当前接口只能查询登录员工本人的采购申请")
    requirements, total = await service.list_mine(
        actor=actor,
        status=requirement_status,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse(
        data=requirements,
        page=PageInfo(number=page, size=page_size, total=total),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@router.get(
    "/{requirement_id}",
    response_model=SuccessResponse[RequirementDetail],
    summary="查看一张采购申请的完整内容",
    description=(
        "根据采购申请 ID 读取数据库中的最新内容。Agent 在让员工确认提交之前必须调用此接口，"
        "避免展示过期的会话缓存。普通员工只能查看自己的申请。"
    ),
)
async def get_requirement_detail(
    requirement_id: int,
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[RequirementService, Depends(get_requirement_service)],
) -> SuccessResponse[RequirementDetail]:
    detail = await service.get_detail(requirement_id, actor)
    return SuccessResponse(
        data=detail,
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@router.patch(
    "/{requirement_id}",
    response_model=SuccessResponse[RequirementDetail],
    summary="修改采购申请草稿",
    description=(
        "补充或纠正草稿字段，只需传本次发生变化的字段。`version` 必须使用上一次响应中的最新值；"
        "每次新的修改操作使用新的 `Idempotency-Key`。只有 DRAFT 状态可以修改。"
    ),
)
async def update_requirement_draft(
    requirement_id: int,
    payload: UpdateRequirementDraft,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[RequirementService, Depends(get_requirement_service)],
) -> SuccessResponse[RequirementDetail]:
    detail = await service.update_draft(
        requirement_id,
        payload,
        _audit_context(request, actor, idempotency_key),
    )
    return SuccessResponse(
        data=detail,
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@router.post(
    "/{requirement_id}/submit",
    response_model=SuccessResponse[RequirementSubmissionResult],
    summary="员工确认并提交审批",
    description=(
        "员工核对采购单并明确确认后调用。`confirmed` 必须为 true；申请原因、具体申请地点、"
        "设备名称和数量缺失时后端会拒绝提交，其他采购字段均可留空。"
        "成功后状态变为 PENDING_APPROVAL（待审批），并记录提交时间和状态历史。"
    ),
)
async def submit_requirement(
    requirement_id: int,
    payload: SubmitRequirement,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[RequirementService, Depends(get_requirement_service)],
) -> SuccessResponse[RequirementSubmissionResult]:
    result = await service.submit(
        requirement_id,
        payload,
        _audit_context(request, actor, idempotency_key),
    )
    return SuccessResponse(
        data=result,
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@router.post(
    "/{requirement_id}/cancel",
    response_model=SuccessResponse[RequirementDetail],
    summary="取消尚未提交的采购草稿",
    description=(
        "员工明确决定不再采购时调用。只允许取消本人处于 DRAFT 状态的草稿；"
        "必须填写取消原因、当前版本和新的 `Idempotency-Key`。"
    ),
)
async def cancel_requirement_draft(
    requirement_id: int,
    payload: CancelRequirementDraft,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[RequirementService, Depends(get_requirement_service)],
) -> SuccessResponse[RequirementDetail]:
    detail = await service.cancel_draft(
        requirement_id,
        payload,
        _audit_context(request, actor, idempotency_key),
    )
    return SuccessResponse(
        data=detail,
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@router.post(
    "/{requirement_id}/revise",
    response_model=SuccessResponse[RequirementDetail],
    status_code=status.HTTP_201_CREATED,
    summary="基于被驳回申请创建修改草稿",
    description="保留原申请和审批记录，复制业务内容形成下一版本草稿，员工修改完整后可重新提交审批。",
)
async def revise_rejected_requirement(
    requirement_id: int,
    payload: ReviseRejectedRequirement,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[RequirementService, Depends(get_requirement_service)],
) -> SuccessResponse[RequirementDetail]:
    detail = await service.revise_rejected(
        requirement_id,
        payload,
        _audit_context(request, actor, idempotency_key),
    )
    return SuccessResponse(
        data=detail,
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@recommendation_router.post(
    "/historical-suppliers/search",
    response_model=SuccessResponse[HistoricalSupplierRecommendationResult],
    summary="根据历史采购推荐供应商",
    description=(
        "读取当前草稿中的商品信息，查询相似的已完成采购单，返回历史供应商、采购次数、历史价格、"
        "订单号和匹配理由。推荐只供员工参考，不会自动修改草稿，也不会限制员工选择其他供应商。"
    ),
)
async def search_historical_suppliers(
    payload: HistoricalSupplierQuery,
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[RequirementService, Depends(get_requirement_service)],
) -> SuccessResponse[HistoricalSupplierRecommendationResult]:
    result = await service.search_historical_suppliers(payload, actor)
    return SuccessResponse(
        data=result,
        meta=ResponseMeta(request_id=request.state.request_id),
    )
