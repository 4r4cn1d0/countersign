"""Event ingestion endpoints."""

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from asyncpg import Pool

from api.middleware.auth import get_current_user
from models.trace_event import (
    AnnotationEvent,
    CustomMetricEvent,
    DecisionPointEvent,
    ErrorDetail,
    EventBatchRequest,
    EventBatchResponse,
    MemoryAccessEvent,
    PlanningPhaseEvent,
    ReasoningStepEvent,
    ToolCallEvent,
)
from services.auth import TokenData
from services.database import get_db_pool
from services.message_queue import MessageQueueProducer
from api.routes.event_compression import expand_batch_events

router = APIRouter()

EVENT_MODEL_MAP = {
    "reasoning_step": ReasoningStepEvent,
    "tool_call": ToolCallEvent,
    "memory_access": MemoryAccessEvent,
    "decision_point": DecisionPointEvent,
    "planning_phase": PlanningPhaseEvent,
    "custom_metric": CustomMetricEvent,
    "annotation": AnnotationEvent,
}


async def _authorize_session_owner(
    session_id: UUID,
    current_user: TokenData,
    pool: Pool
) -> None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT session_id FROM sessions WHERE session_id = $1 AND user_id = $2",
            session_id,
            current_user.user_id,
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or access denied"
        )


def _parse_trace_event(event_data: Dict[str, Any], session_id: UUID) -> Dict[str, Any]:
    event_type = event_data.get("event_type")
    model_cls = EVENT_MODEL_MAP.get(event_type)

    if model_cls is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported event_type: {event_type}"
        )

    try:
        event = model_cls.model_validate(event_data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)
        )

    if event.session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id in event payload must match path parameter"
        )

    return event.model_dump(mode="json")


@router.post(
    "/sessions/{session_id}/events",
    response_model=EventBatchResponse,
    status_code=status.HTTP_202_ACCEPTED
)
async def append_events(
    session_id: UUID = Path(..., description="Session UUID"),
    request: EventBatchRequest = Body(...),
    current_user: TokenData = Depends(get_current_user),
    pool: Pool = Depends(get_db_pool)
):
    """Append trace events to a session."""
    await _authorize_session_owner(session_id, current_user, pool)

    if not request.events:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one event is required"
        )

    accepted = []
    errors = []

    for index, event_data in enumerate(request.events):
        try:
            accepted.append(_parse_trace_event(event_data, session_id))
        except HTTPException as exc:
            errors.append(ErrorDetail(
                index=index,
                error=str(exc.detail)
            ))

    if accepted:
        producer = MessageQueueProducer()
        await producer.publish_batch(accepted)

    return EventBatchResponse(
        accepted_count=len(accepted),
        rejected_count=len(errors),
        errors=errors
    )


@router.post(
    "/sessions/{session_id}/events/batch",
    response_model=EventBatchResponse,
    status_code=status.HTTP_202_ACCEPTED
)
async def batch_upload_events(
    session_id: UUID = Path(..., description="Session UUID"),
    request: EventBatchRequest = None,
    current_user: TokenData = Depends(get_current_user),
    pool: Pool = Depends(get_db_pool)
):
    """Bulk upload events with optional compression."""
    await _authorize_session_owner(session_id, current_user, pool)

    if request is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Request body is required",
        )

    if request.compression and request.compression not in {"gzip", "zstd"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported compression type",
        )

    event_list = expand_batch_events(request)
    if not event_list:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one event is required",
        )

    accepted = []
    errors = []

    for index, event_data in enumerate(event_list):
        try:
            accepted.append(_parse_trace_event(event_data, session_id))
        except HTTPException as exc:
            errors.append(ErrorDetail(
                index=index,
                error=str(exc.detail)
            ))

    if accepted:
        producer = MessageQueueProducer()
        await producer.publish_batch(accepted)

    return EventBatchResponse(
        accepted_count=len(accepted),
        rejected_count=len(errors),
        errors=errors
    )
