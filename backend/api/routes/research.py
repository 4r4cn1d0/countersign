"""Research analysis endpoints."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.middleware.auth import get_current_user
from services.auth import TokenData

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.runner import build_memory_health_report  # noqa: E402

router = APIRouter()


class MemoryHealthReportRequest(BaseModel):
    """Request body for scoring a benchmark run."""

    run: Dict[str, Any]
    task: Optional[Dict[str, Any]] = None


class MemoryHealthReportResponse(BaseModel):
    """Memory-health report response."""

    schema_version: str
    run_id: Optional[str] = None
    task_id: Optional[str] = None
    metrics: Dict[str, float]
    claim_counts: Dict[str, int]
    unsupported_claims: list[Dict[str, Any]]
    stale_claims: list[Dict[str, Any]]
    contradicted_claims: list[Dict[str, Any]]
    recovery_opportunities: list[Dict[str, Any]]
    trace_event_count: int


@router.post(
    "/research/memory-health",
    response_model=MemoryHealthReportResponse,
)
async def create_memory_health_report(
    request: MemoryHealthReportRequest,
    current_user: TokenData = Depends(get_current_user),
) -> Dict[str, Any]:
    """Score a submitted benchmark run for memory corruption indicators."""

    # Authentication is enough here; the submitted run is not read from shared storage.
    _ = current_user
    return build_memory_health_report(request.run, request.task)
