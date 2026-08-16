"""Trace event data models and Pydantic schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ErrorInfo(BaseModel):
    """Error information for failed events."""
    
    error_type: str
    message: str
    stack_trace: Optional[str] = None
    recoverable: bool = False
    retry_attempted: bool = False
    context: Optional[Dict[str, Any]] = None


class TraceEvent(BaseModel):
    """Base class for all trace events."""
    
    event_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    event_type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    sequence_number: int
    parent_event_id: Optional[UUID] = None
    
    # Common fields
    duration_ms: Optional[int] = None
    status: Optional[str] = None
    error: Optional[ErrorInfo] = None
    
    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }


class ReasoningStepEvent(TraceEvent):
    """Reasoning step event with LLM call details."""
    
    event_type: str = "reasoning_step"
    
    # Prompt and response
    prompt: str
    response: str
    
    # LLM call details
    model: str
    temperature: float = 0.7
    max_tokens: int = 1000
    input_tokens: int
    output_tokens: int
    cost: Decimal
    
    # Reasoning metadata
    reasoning_type: Optional[str] = None  # "planning", "decision", "reflection"
    chain_of_thought: Optional[str] = None
    
    # Derived metrics
    entropy: Optional[float] = None
    confidence: Optional[float] = None


class ToolCallEvent(TraceEvent):
    """Tool call event with execution details."""
    
    event_type: str = "tool_call"
    
    # Tool details
    tool_name: str
    tool_type: str  # "api", "function", "database"
    
    # Input/output
    inputs: Dict[str, Any]
    outputs: Optional[Dict[str, Any]] = None
    
    # Execution details
    start_time: datetime
    end_time: Optional[datetime] = None
    retry_count: int = 0
    
    # Error handling
    stack_trace: Optional[str] = None


class MemoryItem(BaseModel):
    """Memory item retrieved from memory access."""
    
    content: str
    relevance_score: float
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime


class MemoryAccessEvent(TraceEvent):
    """Memory access event with retrieval details."""
    
    event_type: str = "memory_access"
    
    # Query details
    query: str
    memory_type: str  # "short_term", "long_term", "episodic"
    retrieval_method: str  # "semantic_search", "key_lookup", "recency"
    
    # Results
    num_results: int
    results: List[MemoryItem]


class DecisionCandidate(BaseModel):
    """Candidate action in a decision point."""
    
    candidate_id: str
    action: str
    score: Optional[float] = None
    reasoning: Optional[str] = None


class DecisionPointEvent(TraceEvent):
    """Decision point event with candidate actions."""
    
    event_type: str = "decision_point"
    
    # Decision context
    decision_type: str  # "action_selection", "path_choice", "termination"
    context: str
    
    # Options
    candidates: List[DecisionCandidate]
    selected_candidate_id: str
    
    # Reasoning
    reasoning: str


class SubTask(BaseModel):
    """Sub-task in a planning phase."""
    
    task_id: str
    description: str
    dependencies: List[str] = Field(default_factory=list)
    status: str = "pending"  # "pending", "in_progress", "completed", "failed"
    assigned_to: Optional[str] = None


class PlanningPhaseEvent(TraceEvent):
    """Planning phase event with task decomposition."""
    
    event_type: str = "planning_phase"
    
    # Planning details
    goal: str
    sub_tasks: List[SubTask]
    planning_strategy: str  # "hierarchical", "sequential", "parallel"
    
    # Revision tracking
    is_revision: bool = False
    previous_plan_id: Optional[UUID] = None
    revision_reason: Optional[str] = None


class CustomMetricEvent(TraceEvent):
    """Custom metric event for user-defined metrics."""
    
    event_type: str = "custom_metric"
    
    # Metric details
    metric_name: str
    metric_value: Union[int, float, str, bool]
    metric_type: str  # "counter", "gauge", "histogram"
    unit: Optional[str] = None
    
    # Context
    tags: Optional[Dict[str, str]] = None


class AnnotationEvent(TraceEvent):
    """Annotation event for user notes."""
    
    event_type: str = "annotation"
    
    # Annotation details
    text: str
    annotation_type: str  # "note", "warning", "milestone"
    related_event_ids: List[UUID] = Field(default_factory=list)


# Union type for all event types
AnyTraceEvent = Union[
    ReasoningStepEvent,
    ToolCallEvent,
    MemoryAccessEvent,
    DecisionPointEvent,
    PlanningPhaseEvent,
    CustomMetricEvent,
    AnnotationEvent
]


class EventBatchRequest(BaseModel):
    """Request model for batch event ingestion."""
    
    events: List[Dict[str, Any]] = Field(default_factory=list)
    compression: Optional[str] = None  # "gzip", "zstd"
    compressed_payload: Optional[str] = None  # base64-encoded compressed JSON array of events


class ErrorDetail(BaseModel):
    """Error detail for batch response."""
    index: Union[int, str]
    error: str


class EventBatchResponse(BaseModel):
    """Response model for batch event ingestion."""
    
    accepted_count: int
    rejected_count: int
    errors: List[ErrorDetail] = Field(default_factory=list)
