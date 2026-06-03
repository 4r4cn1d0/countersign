"""Session data model and Pydantic schemas."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    """Session execution status."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class Session(BaseModel):
    """Agent execution session with aggregated metrics."""
    
    session_id: UUID = Field(default_factory=uuid4)
    user_id: str
    agent_type: str
    goal: str
    status: SessionStatus = SessionStatus.RUNNING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    
    # Aggregated metrics
    total_reasoning_steps: int = 0
    total_tool_calls: int = 0
    total_memory_accesses: int = 0
    total_memory_hits: int = 0
    total_tokens: int = 0
    total_cost: Decimal = Decimal("0.0")
    error_count: int = 0
    
    # Metadata
    metadata: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)
    coordination_id: Optional[UUID] = None
    
    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat(),
            Decimal: float
        }


class SessionCreate(BaseModel):
    """Request model for creating a new session."""
    
    goal: str = Field(..., min_length=1, max_length=5000)
    agent_type: str = Field(..., min_length=1, max_length=50)
    metadata: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)
    coordination_id: Optional[UUID] = None


class SessionResponse(BaseModel):
    """Response model for session data."""
    
    session_id: UUID
    user_id: str
    agent_type: str
    goal: str
    status: SessionStatus
    created_at: datetime
    completed_at: Optional[datetime]
    duration_ms: Optional[int]
    
    total_reasoning_steps: int
    total_tool_calls: int
    total_memory_accesses: int
    total_memory_hits: int = 0
    total_tokens: int
    total_cost: float
    error_count: int
    
    metadata: Optional[Dict[str, Any]]
    tags: List[str]
    coordination_id: Optional[UUID]
    
    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }


class SessionListResponse(BaseModel):
    """Response model for session list."""
    
    sessions: List[SessionResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class SessionSearchRequest(BaseModel):
    """Request model for session search."""
    
    query: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    sort: str = "created_at:desc"
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)
