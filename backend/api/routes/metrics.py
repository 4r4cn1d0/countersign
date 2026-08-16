"""Metrics and analytics endpoints."""

from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, status
from asyncpg import Pool
from pydantic import BaseModel

from api.middleware.auth import get_current_user
from services.auth import TokenData
from services.database import get_db_pool

router = APIRouter()


# Response models
class SessionStatistic(BaseModel):
    """Statistic for a single session."""
    session_id: str
    status: str
    duration_ms: Optional[int] = None
    total_tokens: int
    total_cost: float
    reasoning_steps: int
    tool_calls: int
    success: bool


class AggregateMetricsResponse(BaseModel):
    """Response model for aggregate metrics."""
    time_period_start: str
    time_period_end: str
    total_sessions: int
    completed_sessions: int
    failed_sessions: int
    success_rate: float
    
    # Statistics
    avg_duration_ms: float
    median_duration_ms: float
    p95_duration_ms: float
    
    total_tokens_used: int
    avg_tokens_per_session: float
    
    total_cost: float
    avg_cost_per_session: float
    
    total_reasoning_steps: int
    avg_reasoning_steps_per_session: float
    
    total_tool_calls: int
    avg_tool_calls_per_session: float
    
    error_count: int


class TimeSeriesDataPoint(BaseModel):
    """Data point in time-series data."""
    timestamp: str
    value: float
    metric_name: str


class TimeSeriesMetricsResponse(BaseModel):
    """Response model for time-series metrics."""
    metric_name: str
    time_period_start: str
    time_period_end: str
    data_points: List[TimeSeriesDataPoint]


async def _get_user_sessions_filter(current_user: TokenData) -> str:
    """Get SQL filter for user's sessions."""
    return f"WHERE s.user_id = '{current_user.user_id}'"


@router.get(
    "/metrics/aggregate",
    response_model=AggregateMetricsResponse,
    status_code=status.HTTP_200_OK
)
async def get_aggregate_metrics(
    days: int = Query(7, ge=1, le=365),
    current_user: TokenData = Depends(get_current_user),
    pool: Pool = Depends(get_db_pool)
):
    """
    Get aggregate metrics across all sessions for current user.
    
    Args:
        days: Number of days to look back (default: 7, max: 365)
        current_user: Authenticated user
        pool: Database connection pool
    
    Returns:
        AggregateMetricsResponse with aggregated statistics
    """
    time_period_start = datetime.utcnow() - timedelta(days=days)
    time_period_end = datetime.utcnow()

    async with pool.acquire() as conn:
        # Get aggregate statistics for sessions
        agg_row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) as total_sessions,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_sessions,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_sessions,
                AVG(CAST(duration_ms AS FLOAT)) as avg_duration_ms,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_ms) as median_duration_ms,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_duration_ms,
                SUM(total_tokens) as total_tokens_used,
                AVG(total_tokens) as avg_tokens_per_session,
                SUM(total_cost) as total_cost,
                AVG(total_cost) as avg_cost_per_session,
                SUM(total_reasoning_steps) as total_reasoning_steps,
                AVG(total_reasoning_steps) as avg_reasoning_steps_per_session,
                SUM(total_tool_calls) as total_tool_calls,
                AVG(total_tool_calls) as avg_tool_calls_per_session,
                SUM(error_count) as error_count
            FROM sessions
            WHERE user_id = $1 AND created_at >= $2
            """,
            current_user.user_id,
            time_period_start
        )

    if not agg_row or agg_row["total_sessions"] is None:
        # Return empty metrics if no sessions
        return AggregateMetricsResponse(
            time_period_start=time_period_start.isoformat(),
            time_period_end=time_period_end.isoformat(),
            total_sessions=0,
            completed_sessions=0,
            failed_sessions=0,
            success_rate=0.0,
            avg_duration_ms=0.0,
            median_duration_ms=0.0,
            p95_duration_ms=0.0,
            total_tokens_used=0,
            avg_tokens_per_session=0.0,
            total_cost=0.0,
            avg_cost_per_session=0.0,
            total_reasoning_steps=0,
            avg_reasoning_steps_per_session=0.0,
            total_tool_calls=0,
            avg_tool_calls_per_session=0.0,
            error_count=0
        )

    total_sessions = agg_row["total_sessions"] or 0
    completed_sessions = agg_row["completed_sessions"] or 0
    success_rate = (completed_sessions / total_sessions) if total_sessions > 0 else 0.0

    return AggregateMetricsResponse(
        time_period_start=time_period_start.isoformat(),
        time_period_end=time_period_end.isoformat(),
        total_sessions=total_sessions,
        completed_sessions=completed_sessions,
        failed_sessions=agg_row["failed_sessions"] or 0,
        success_rate=success_rate,
        avg_duration_ms=float(agg_row["avg_duration_ms"]) if agg_row["avg_duration_ms"] else 0.0,
        median_duration_ms=float(agg_row["median_duration_ms"]) if agg_row["median_duration_ms"] else 0.0,
        p95_duration_ms=float(agg_row["p95_duration_ms"]) if agg_row["p95_duration_ms"] else 0.0,
        total_tokens_used=agg_row["total_tokens_used"] or 0,
        avg_tokens_per_session=float(agg_row["avg_tokens_per_session"]) if agg_row["avg_tokens_per_session"] else 0.0,
        total_cost=float(agg_row["total_cost"]) if agg_row["total_cost"] else 0.0,
        avg_cost_per_session=float(agg_row["avg_cost_per_session"]) if agg_row["avg_cost_per_session"] else 0.0,
        total_reasoning_steps=agg_row["total_reasoning_steps"] or 0,
        avg_reasoning_steps_per_session=float(agg_row["avg_reasoning_steps_per_session"]) if agg_row["avg_reasoning_steps_per_session"] else 0.0,
        total_tool_calls=agg_row["total_tool_calls"] or 0,
        avg_tool_calls_per_session=float(agg_row["avg_tool_calls_per_session"]) if agg_row["avg_tool_calls_per_session"] else 0.0,
        error_count=agg_row["error_count"] or 0
    )


@router.get(
    "/metrics/timeseries",
    response_model=TimeSeriesMetricsResponse,
    status_code=status.HTTP_200_OK
)
async def get_timeseries_metrics(
    metric: str = Query("cost", pattern="^(cost|duration|tokens|success_rate)$"),
    days: int = Query(7, ge=1, le=365),
    bucket_hours: int = Query(24, ge=1, le=168),
    current_user: TokenData = Depends(get_current_user),
    pool: Pool = Depends(get_db_pool)
):
    """
    Get time-series metrics with hourly/daily buckets.
    
    Args:
        metric: Metric to retrieve (cost, duration, tokens, success_rate)
        days: Number of days to look back
        bucket_hours: Hours per bucket (default: 24 for daily)
        current_user: Authenticated user
        pool: Database connection pool
    
    Returns:
        TimeSeriesMetricsResponse with time-series data points
    """
    time_period_start = datetime.utcnow() - timedelta(days=days)
    time_period_end = datetime.utcnow()

    async with pool.acquire() as conn:
        # Query depends on metric type
        if metric == "cost":
            rows = await conn.fetch(
                """
                SELECT 
                    DATE_TRUNC('hour', created_at) as bucket,
                    SUM(total_cost) as value
                FROM sessions
                WHERE user_id = $1 AND created_at >= $2 AND created_at <= $3
                GROUP BY DATE_TRUNC('hour', created_at)
                ORDER BY bucket ASC
                """,
                current_user.user_id,
                time_period_start,
                time_period_end
            )
        elif metric == "duration":
            rows = await conn.fetch(
                """
                SELECT 
                    DATE_TRUNC('hour', created_at) as bucket,
                    AVG(CAST(duration_ms AS FLOAT)) as value
                FROM sessions
                WHERE user_id = $1 AND created_at >= $2 AND created_at <= $3 AND duration_ms IS NOT NULL
                GROUP BY DATE_TRUNC('hour', created_at)
                ORDER BY bucket ASC
                """,
                current_user.user_id,
                time_period_start,
                time_period_end
            )
        elif metric == "tokens":
            rows = await conn.fetch(
                """
                SELECT 
                    DATE_TRUNC('hour', created_at) as bucket,
                    SUM(total_tokens) as value
                FROM sessions
                WHERE user_id = $1 AND created_at >= $2 AND created_at <= $3
                GROUP BY DATE_TRUNC('hour', created_at)
                ORDER BY bucket ASC
                """,
                current_user.user_id,
                time_period_start,
                time_period_end
            )
        else:  # success_rate
            rows = await conn.fetch(
                """
                SELECT 
                    DATE_TRUNC('hour', created_at) as bucket,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)::FLOAT / 
                    COUNT(*) as value
                FROM sessions
                WHERE user_id = $1 AND created_at >= $2 AND created_at <= $3
                GROUP BY DATE_TRUNC('hour', created_at)
                ORDER BY bucket ASC
                """,
                current_user.user_id,
                time_period_start,
                time_period_end
            )

    data_points = [
        TimeSeriesDataPoint(
            timestamp=row["bucket"].isoformat() if row["bucket"] else None,
            value=float(row["value"]) if row["value"] else 0.0,
            metric_name=metric
        )
        for row in rows
    ]

    return TimeSeriesMetricsResponse(
        metric_name=metric,
        time_period_start=time_period_start.isoformat(),
        time_period_end=time_period_end.isoformat(),
        data_points=data_points
    )
