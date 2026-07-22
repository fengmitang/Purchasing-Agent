from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Request

from app.api.dependencies import get_agent_chat_service, get_current_user
from app.modules.agent.chat_schemas import (
    AgentMessageCommand,
    AgentMessageResult,
    ChatHistoryMessage,
    ConversationResetResult,
)
from app.modules.agent.chat_service import AgentChatService
from app.shared.identity import CurrentUser
from app.shared.responses import PageInfo, PaginatedResponse, ResponseMeta, SuccessResponse

router = APIRouter(prefix="/api/v1/agent", tags=["采购 Agent"])

ConversationPath = Annotated[
    str,
    Path(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$"),
]
IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=128),
]


@router.post("/messages", response_model=SuccessResponse[AgentMessageResult])
async def send_agent_message(
    payload: AgentMessageCommand,
    request: Request,
    idempotency_key: IdempotencyHeader,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[AgentChatService, Depends(get_agent_chat_service)],
) -> SuccessResponse[AgentMessageResult]:
    result = await service.send_message(
        payload,
        actor=actor,
        request_id=request.state.request_id,
        idempotency_key=idempotency_key,
    )
    return SuccessResponse(
        data=result,
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=PaginatedResponse[ChatHistoryMessage],
)
async def list_agent_messages(
    conversation_id: ConversationPath,
    request: Request,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[AgentChatService, Depends(get_agent_chat_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[ChatHistoryMessage]:
    messages, total = await service.list_messages(
        conversation_id,
        actor=actor,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse(
        data=messages,
        page=PageInfo(number=page, size=page_size, total=total),
        meta=ResponseMeta(request_id=request.state.request_id),
    )


@router.delete(
    "/conversations/{conversation_id}",
    response_model=SuccessResponse[ConversationResetResult],
)
async def reset_agent_conversation(
    conversation_id: ConversationPath,
    request: Request,
    idempotency_key: IdempotencyHeader,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[AgentChatService, Depends(get_agent_chat_service)],
) -> SuccessResponse[ConversationResetResult]:
    result = await service.reset_conversation(
        conversation_id,
        actor=actor,
        idempotency_key=idempotency_key,
    )
    return SuccessResponse(
        data=result,
        meta=ResponseMeta(request_id=request.state.request_id),
    )
