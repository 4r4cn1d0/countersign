"""Session management endpoints."""

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from asyncpg import Pool

from api.middleware.auth import get_current_user
from models.session import (
    SessionCreate,
    SessionResponse,
    SessionListResponse,
    SessionSearchRequest,
    SessionStatus,
    Session
)
from services.auth import TokenData
from services.database import get_db_pool

router = APIRouter()


def _json_object(value: Any) -> Optional[dict]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    session_data: SessionCreate,
    current_user: TokenData = Depends(get_current_user),
    pool: Pool = Depends(get_db_pool)
):
    """
    Create a new agent session.
    
    Args:
        session_data: Session creation data
        current_user: Authenticated user
        pool: Database connection pool
        
    Returns:
        Created session data
    """
    # Create session object
    session = Session(
        user_id=current_user.user_id,
        agent_type=session_data.agent_type,
        goal=session_data.goal,
        metadata=session_data.metadata,
        tags=session_data.tags,
        coordination_id=session_data.coordination_id
    )
    
    # Insert into database
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sessions (
                session_id, user_id, agent_type, goal, status,
                created_at, metadata, tags, coordination_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            session.session_id,
            session.user_id,
            session.agent_type,
            session.goal,
            session.status.value,
            session.created_at,
            session.metadata,
            session.tags,
            session.coordination_id
        )
    
    # Return response
    return SessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        agent_type=session.agent_type,
        goal=session.goal,
        status=session.status,
        created_at=session.created_at,
        completed_at=session.completed_at,
        duration_ms=session.duration_ms,
        total_reasoning_steps=session.total_reasoning_steps,
        total_tool_calls=session.total_tool_calls,
        total_memory_accesses=session.total_memory_accesses,
        total_tokens=session.total_tokens,
        total_cost=float(session.total_cost),
        error_count=session.error_count,
        metadata=session.metadata,
        tags=session.tags,
        coordination_id=session.coordination_id
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    pool: Pool = Depends(get_db_pool)
):
    """
    Retrieve session by ID.
    
    Args:
        session_id: Session UUID
        current_user: Authenticated user
        pool: Database connection pool
        
    Returns:
        Session data
        
    Raises:
        HTTPException: If session not found or access denied
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 
                session_id, user_id, agent_type, goal, status,
                created_at, completed_at, duration_ms,
                total_reasoning_steps, total_tool_calls, total_memory_accesses,
                total_tokens, total_cost, error_count,
                metadata, tags, coordination_id
            FROM sessions
            WHERE session_id = $1
            """,
            session_id
        )
    
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check access permission
    if row["user_id"] != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return SessionResponse(
        session_id=row["session_id"],
        user_id=row["user_id"],
        agent_type=row["agent_type"],
        goal=row["goal"],
        status=SessionStatus(row["status"]),
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        duration_ms=row["duration_ms"],
        total_reasoning_steps=row["total_reasoning_steps"],
        total_tool_calls=row["total_tool_calls"],
        total_memory_accesses=row["total_memory_accesses"],
        total_tokens=row["total_tokens"],
        total_cost=float(row["total_cost"]) if row["total_cost"] else 0.0,
        error_count=row["error_count"],
        metadata=_json_object(row["metadata"]),
        tags=row["tags"] or [],
        coordination_id=row["coordination_id"]
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    status: Optional[str] = Query(None, description="Filter by status"),
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    limit: int = Query(50, ge=1, le=500, description="Number of results per page"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    sort: str = Query("created_at:desc", description="Sort field and direction"),
    current_user: TokenData = Depends(get_current_user),
    pool: Pool = Depends(get_db_pool)
):
    """
    List sessions with filtering and pagination.
    
    Args:
        status: Filter by session status
        agent_type: Filter by agent type
        limit: Maximum number of results
        offset: Number of results to skip
        sort: Sort field and direction (e.g., "created_at:desc")
        current_user: Authenticated user
        pool: Database connection pool
        
    Returns:
        Paginated list of sessions
    """
    # Build WHERE clause
    where_clauses = ["user_id = $1"]
    params = [current_user.user_id]
    param_count = 1
    
    if status:
        param_count += 1
        where_clauses.append(f"status = ${param_count}")
        params.append(status)
    
    if agent_type:
        param_count += 1
        where_clauses.append(f"agent_type = ${param_count}")
        params.append(agent_type)
    
    where_clause = " AND ".join(where_clauses)
    
    # Parse sort parameter
    sort_parts = sort.split(":")
    sort_field = sort_parts[0] if len(sort_parts) > 0 else "created_at"
    sort_direction = sort_parts[1].upper() if len(sort_parts) > 1 else "DESC"
    
    # Validate sort field
    valid_sort_fields = [
        "created_at", "completed_at", "duration_ms", "total_cost",
        "total_tokens", "status", "agent_type"
    ]
    if sort_field not in valid_sort_fields:
        sort_field = "created_at"
    
    if sort_direction not in ["ASC", "DESC"]:
        sort_direction = "DESC"
    
    async with pool.acquire() as conn:
        # Get total count
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM sessions WHERE {where_clause}",
            *params
        )
        
        # Get paginated results
        rows = await conn.fetch(
            f"""
            SELECT 
                session_id, user_id, agent_type, goal, status,
                created_at, completed_at, duration_ms,
                total_reasoning_steps, total_tool_calls, total_memory_accesses,
                total_tokens, total_cost, error_count,
                metadata, tags, coordination_id
            FROM sessions
            WHERE {where_clause}
            ORDER BY {sort_field} {sort_direction}
            LIMIT ${param_count + 1} OFFSET ${param_count + 2}
            """,
            *params, limit, offset
        )
    
    sessions = [
        SessionResponse(
            session_id=row["session_id"],
            user_id=row["user_id"],
            agent_type=row["agent_type"],
            goal=row["goal"],
            status=SessionStatus(row["status"]),
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            duration_ms=row["duration_ms"],
            total_reasoning_steps=row["total_reasoning_steps"],
            total_tool_calls=row["total_tool_calls"],
            total_memory_accesses=row["total_memory_accesses"],
            total_tokens=row["total_tokens"],
            total_cost=float(row["total_cost"]) if row["total_cost"] else 0.0,
            error_count=row["error_count"],
            metadata=_json_object(row["metadata"]),
            tags=row["tags"] or [],
            coordination_id=row["coordination_id"]
        )
        for row in rows
    ]
    
    return SessionListResponse(
        sessions=sessions,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(sessions)) < total
    )


@router.post("/sessions/search", response_model=SessionListResponse)
async def search_sessions(
    search_request: SessionSearchRequest,
    current_user: TokenData = Depends(get_current_user),
    pool: Pool = Depends(get_db_pool)
):
    """
    Full-text search across sessions with advanced filtering.
    
    Args:
        search_request: Search parameters and filters
        current_user: Authenticated user
        pool: Database connection pool
        
    Returns:
        Paginated list of matching sessions
    """
    # Build WHERE clause
    where_clauses = ["user_id = $1"]
    params = [current_user.user_id]
    param_count = 1
    
    # Full-text search on goal
    if search_request.query:
        param_count += 1
        where_clauses.append(
            f"(to_tsvector('english', goal) @@ plainto_tsquery('english', ${param_count}) "
            f"OR goal ILIKE ${param_count + 1})"
        )
        params.append(search_request.query)
        param_count += 1
        params.append(f"%{search_request.query}%")
    
    # Apply filters
    if search_request.filters:
        filters = search_request.filters
        
        # Status filter
        if "status" in filters and filters["status"]:
            status_list = filters["status"]
            if isinstance(status_list, list) and status_list:
                param_count += 1
                where_clauses.append(f"status = ANY(${param_count})")
                params.append(status_list)
        
        # Date range filter
        if "date_range" in filters and filters["date_range"]:
            date_range = filters["date_range"]
            if "start" in date_range:
                param_count += 1
                where_clauses.append(f"created_at >= ${param_count}")
                params.append(datetime.fromisoformat(date_range["start"].replace("Z", "+00:00")))
            if "end" in date_range:
                param_count += 1
                where_clauses.append(f"created_at <= ${param_count}")
                params.append(datetime.fromisoformat(date_range["end"].replace("Z", "+00:00")))
        
        # Cost range filter
        if "cost_range" in filters and filters["cost_range"]:
            cost_range = filters["cost_range"]
            if "min" in cost_range:
                param_count += 1
                where_clauses.append(f"total_cost >= ${param_count}")
                params.append(Decimal(str(cost_range["min"])))
            if "max" in cost_range:
                param_count += 1
                where_clauses.append(f"total_cost <= ${param_count}")
                params.append(Decimal(str(cost_range["max"])))

        # Duration range filter
        if "duration_range" in filters and filters["duration_range"]:
            duration_range = filters["duration_range"]
            if "min" in duration_range:
                param_count += 1
                where_clauses.append(f"duration_ms >= ${param_count}")
                params.append(int(duration_range["min"]))
            if "max" in duration_range:
                param_count += 1
                where_clauses.append(f"duration_ms <= ${param_count}")
                params.append(int(duration_range["max"]))
        
        # Tags filter
        if "tags" in filters and filters["tags"]:
            tags_list = filters["tags"]
            if isinstance(tags_list, list) and tags_list:
                param_count += 1
                where_clauses.append(f"tags && ${param_count}")
                params.append(tags_list)
        
        # Agent type filter
        if "agent_type" in filters and filters["agent_type"]:
            param_count += 1
            where_clauses.append(f"agent_type = ${param_count}")
            params.append(filters["agent_type"])
    
    where_clause = " AND ".join(where_clauses)
    
    # Parse sort parameter
    sort_parts = search_request.sort.split(":")
    sort_field = sort_parts[0] if len(sort_parts) > 0 else "created_at"
    sort_direction = sort_parts[1].upper() if len(sort_parts) > 1 else "DESC"
    
    # Validate sort field
    valid_sort_fields = [
        "created_at", "completed_at", "duration_ms", "total_cost",
        "total_tokens", "status", "agent_type"
    ]
    if sort_field not in valid_sort_fields:
        sort_field = "created_at"
    
    if sort_direction not in ["ASC", "DESC"]:
        sort_direction = "DESC"
    
    async with pool.acquire() as conn:
        # Get total count
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM sessions WHERE {where_clause}",
            *params
        )
        
        # Get paginated results
        rows = await conn.fetch(
            f"""
            SELECT 
                session_id, user_id, agent_type, goal, status,
                created_at, completed_at, duration_ms,
                total_reasoning_steps, total_tool_calls, total_memory_accesses,
                total_tokens, total_cost, error_count,
                metadata, tags, coordination_id
            FROM sessions
            WHERE {where_clause}
            ORDER BY {sort_field} {sort_direction}
            LIMIT ${param_count + 1} OFFSET ${param_count + 2}
            """,
            *params, search_request.limit, search_request.offset
        )
    
    sessions = [
        SessionResponse(
            session_id=row["session_id"],
            user_id=row["user_id"],
            agent_type=row["agent_type"],
            goal=row["goal"],
            status=SessionStatus(row["status"]),
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            duration_ms=row["duration_ms"],
            total_reasoning_steps=row["total_reasoning_steps"],
            total_tool_calls=row["total_tool_calls"],
            total_memory_accesses=row["total_memory_accesses"],
            total_tokens=row["total_tokens"],
            total_cost=float(row["total_cost"]) if row["total_cost"] else 0.0,
            error_count=row["error_count"],
            metadata=_json_object(row["metadata"]),
            tags=row["tags"] or [],
            coordination_id=row["coordination_id"]
        )
        for row in rows
    ]
    
    return SessionListResponse(
        sessions=sessions,
        total=total,
        limit=search_request.limit,
        offset=search_request.offset,
        has_more=(search_request.offset + len(sessions)) < total
    )
