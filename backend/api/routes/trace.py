"""Trace retrieval and analysis endpoints."""

import json
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from asyncpg import Pool
from pydantic import BaseModel

from api.middleware.auth import get_current_user
from services.auth import TokenData
from services.database import get_db_pool

router = APIRouter()


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _json_object(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


# Response models
class TraceEventResponse(BaseModel):
    """Response model for a single trace event."""
    event_id: str
    session_id: str
    event_type: str
    timestamp: str
    sequence_number: int
    duration_ms: Optional[int] = None
    status: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    event_data: Dict[str, Any]


class TraceResponse(BaseModel):
    """Response model for complete trace retrieval."""
    session_id: str
    total_events: int
    events: List[TraceEventResponse]
    page: int
    page_size: int
    has_more: bool


class ExecutionGraphNode(BaseModel):
    """Node in execution graph."""
    event_id: str
    event_type: str
    label: str
    duration_ms: Optional[int] = None
    status: Optional[str] = None
    timestamp: str


class ExecutionGraphEdge(BaseModel):
    """Edge in execution graph (parent-child relationship)."""
    source_event_id: str
    target_event_id: str


class ExecutionGraphResponse(BaseModel):
    """Response model for execution graph."""
    session_id: str
    nodes: List[ExecutionGraphNode]
    edges: List[ExecutionGraphEdge]


class SessionMetricsResponse(BaseModel):
    """Response model for session-level metrics."""
    session_id: str
    goal: str
    status: str
    created_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    
    # Event counts
    total_reasoning_steps: int
    total_tool_calls: int
    total_memory_accesses: int
    total_decision_points: int
    total_planning_phases: int
    error_count: int
    
    # Aggregated metrics
    total_tokens: int
    total_cost: float


async def _authorize_session_owner(
    session_id: UUID,
    current_user: TokenData,
    pool: Pool
) -> None:
    """Verify user owns the session."""
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


@router.get(
    "/sessions/{session_id}/trace",
    response_model=TraceResponse,
    status_code=status.HTTP_200_OK
)
async def get_session_trace(
    session_id: UUID = Path(..., description="Session UUID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    current_user: TokenData = Depends(get_current_user),
    pool: Pool = Depends(get_db_pool)
):
    """Retrieve complete trace for a session with pagination."""
    await _authorize_session_owner(session_id, current_user, pool)

    offset = (page - 1) * page_size

    async with pool.acquire() as conn:
        # Get total event count
        total_row = await conn.fetchval(
            "SELECT COUNT(*) FROM trace_events WHERE session_id = $1",
            session_id
        )
        total_events = total_row or 0

        # Get paginated events
        rows = await conn.fetch(
            """
            SELECT event_id, session_id, event_type, timestamp, sequence_number, 
                   duration_ms, status, error_type, error_message, event_data
            FROM trace_events 
            WHERE session_id = $1 
            ORDER BY sequence_number ASC 
            LIMIT $2 OFFSET $3
            """,
            session_id,
            page_size,
            offset
        )

    events = [
        TraceEventResponse(
            event_id=str(row["event_id"]),
            session_id=str(row["session_id"]),
            event_type=row["event_type"],
            timestamp=row["timestamp"].isoformat() if row["timestamp"] else None,
            sequence_number=row["sequence_number"],
            duration_ms=row["duration_ms"],
            status=row["status"],
            error_type=_row_get(row, "error_type"),
            error_message=_row_get(row, "error_message"),
            event_data=_json_object(row["event_data"])
        )
        for row in rows
    ]

    has_more = (offset + page_size) < total_events

    return TraceResponse(
        session_id=str(session_id),
        total_events=total_events,
        events=events,
        page=page,
        page_size=page_size,
        has_more=has_more
    )


@router.get(
    "/sessions/{session_id}/graph",
    response_model=ExecutionGraphResponse,
    status_code=status.HTTP_200_OK
)
async def get_execution_graph(
    session_id: UUID = Path(..., description="Session UUID"),
    current_user: TokenData = Depends(get_current_user),
    pool: Pool = Depends(get_db_pool)
):
    """Retrieve execution graph showing parent-child relationships."""
    await _authorize_session_owner(session_id, current_user, pool)

    async with pool.acquire() as conn:
        # Get all events with parent-child info
        rows = await conn.fetch(
            """
            SELECT event_id, event_type, timestamp, sequence_number, 
                   duration_ms, status, parent_event_id, event_data
            FROM trace_events 
            WHERE session_id = $1 
            ORDER BY sequence_number ASC
            """,
            session_id
        )

    nodes = []
    edges = []
    event_map = {}

    for row in rows:
        event_id = str(row["event_id"])
        event_type = row["event_type"]
        event_data = _json_object(row["event_data"])
        
        # Create descriptive label based on event type
        if event_type == "reasoning_step":
            label = f"Reasoning: {event_data.get('model', 'unknown')}"
        elif event_type == "tool_call":
            label = f"Tool: {event_data.get('tool_name', 'unknown')}"
        elif event_type == "memory_access":
            label = f"Memory: {event_data.get('memory_type', 'unknown')}"
        elif event_type == "decision_point":
            label = f"Decision: {event_data.get('decision_type', 'unknown')}"
        elif event_type == "planning_phase":
            label = f"Plan: {event_data.get('planning_strategy', 'unknown')}"
        else:
            label = event_type

        node = ExecutionGraphNode(
            event_id=event_id,
            event_type=event_type,
            label=label,
            duration_ms=row["duration_ms"],
            status=row["status"],
            timestamp=row["timestamp"].isoformat() if row["timestamp"] else None
        )
        nodes.append(node)
        event_map[event_id] = node

        # Create edge if there's a parent
        if row["parent_event_id"]:
            parent_id = str(row["parent_event_id"])
            edge = ExecutionGraphEdge(
                source_event_id=parent_id,
                target_event_id=event_id
            )
            edges.append(edge)

    return ExecutionGraphResponse(
        session_id=str(session_id),
        nodes=nodes,
        edges=edges
    )


@router.get(
    "/sessions/{session_id}/metrics",
    response_model=SessionMetricsResponse,
    status_code=status.HTTP_200_OK
)
async def get_session_metrics(
    session_id: UUID = Path(..., description="Session UUID"),
    current_user: TokenData = Depends(get_current_user),
    pool: Pool = Depends(get_db_pool)
):
    """Retrieve aggregated session metrics."""
    await _authorize_session_owner(session_id, current_user, pool)

    async with pool.acquire() as conn:
        # Get session metadata
        session_row = await conn.fetchrow(
            """
            SELECT session_id, goal, status, created_at, completed_at, duration_ms,
                   total_reasoning_steps, total_tool_calls, total_memory_accesses, 
                   total_tokens, total_cost, error_count
            FROM sessions 
            WHERE session_id = $1
            """,
            session_id
        )

        if not session_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )

        # Count event types in trace
        event_counts = await conn.fetch(
            """
            SELECT event_type, COUNT(*) as count
            FROM trace_events 
            WHERE session_id = $1 
            GROUP BY event_type
            """,
            session_id
        )

    event_type_counts = {row["event_type"]: row["count"] for row in event_counts}

    return SessionMetricsResponse(
        session_id=str(session_row["session_id"]),
        goal=session_row["goal"],
        status=session_row["status"],
        created_at=session_row["created_at"].isoformat() if session_row["created_at"] else None,
        completed_at=session_row["completed_at"].isoformat() if session_row["completed_at"] else None,
        duration_ms=session_row["duration_ms"],
        total_reasoning_steps=event_type_counts.get("reasoning_step", 0),
        total_tool_calls=event_type_counts.get("tool_call", 0),
        total_memory_accesses=event_type_counts.get("memory_access", 0),
        total_decision_points=event_type_counts.get("decision_point", 0),
        total_planning_phases=event_type_counts.get("planning_phase", 0),
        error_count=session_row["error_count"],
        total_tokens=session_row["total_tokens"],
        total_cost=float(session_row["total_cost"])
    )
