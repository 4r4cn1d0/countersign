"""Tests for data models."""

import pytest
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from models.session import (
    Session, 
    SessionStatus, 
    SessionCreate,
    SessionResponse,
    SessionListResponse,
    SessionSearchRequest
)
from models.trace_event import (
    ReasoningStepEvent,
    ToolCallEvent,
    MemoryAccessEvent,
    DecisionPointEvent,
    PlanningPhaseEvent,
    CustomMetricEvent,
    AnnotationEvent,
    ErrorInfo,
    MemoryItem,
    DecisionCandidate,
    SubTask,
    EventBatchRequest,
    EventBatchResponse
)


# Session Model Tests

def test_session_creation():
    """Test Session model creation with default values."""
    session = Session(
        user_id="user_123",
        agent_type="langchain",
        goal="Test agent execution"
    )
    
    assert session.session_id is not None
    assert session.user_id == "user_123"
    assert session.agent_type == "langchain"
    assert session.goal == "Test agent execution"
    assert session.status == SessionStatus.RUNNING
    assert session.total_reasoning_steps == 0
    assert session.total_cost == Decimal("0.0")
    assert session.metadata is None
    assert session.tags == []
    assert session.coordination_id is None


def test_session_with_metadata():
    """Test Session model with metadata and tags."""
    session = Session(
        user_id="user_456",
        agent_type="autogpt",
        goal="Complex task",
        metadata={"env": "production", "version": "1.0"},
        tags=["production", "critical"]
    )
    
    assert session.metadata == {"env": "production", "version": "1.0"}
    assert len(session.tags) == 2
    assert "production" in session.tags


def test_session_status_enum():
    """Test SessionStatus enum values."""
    assert SessionStatus.RUNNING == "running"
    assert SessionStatus.COMPLETED == "completed"
    assert SessionStatus.FAILED == "failed"
    assert SessionStatus.TIMEOUT == "timeout"
    assert SessionStatus.CANCELLED == "cancelled"


def test_session_create_request():
    """Test SessionCreate request model."""
    request = SessionCreate(
        goal="Research AI safety",
        agent_type="langchain",
        tags=["research", "ai-safety"]
    )
    
    assert request.goal == "Research AI safety"
    assert request.agent_type == "langchain"
    assert len(request.tags) == 2


def test_session_create_validation():
    """Test SessionCreate validation."""
    # Test empty goal validation
    with pytest.raises(Exception):
        SessionCreate(
            goal="",
            agent_type="langchain"
        )


def test_session_response():
    """Test SessionResponse model."""
    response = SessionResponse(
        session_id=uuid4(),
        user_id="user_123",
        agent_type="langchain",
        goal="Test goal",
        status=SessionStatus.COMPLETED,
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        duration_ms=5000,
        total_reasoning_steps=10,
        total_tool_calls=5,
        total_memory_accesses=3,
        total_tokens=1000,
        total_cost=0.50,
        error_count=0,
        metadata=None,
        tags=[],
        coordination_id=None
    )
    
    assert response.status == SessionStatus.COMPLETED
    assert response.total_reasoning_steps == 10


def test_session_list_response():
    """Test SessionListResponse model."""
    response = SessionListResponse(
        sessions=[],
        total=100,
        limit=50,
        offset=0,
        has_more=True
    )
    
    assert response.total == 100
    assert response.has_more is True


def test_session_search_request():
    """Test SessionSearchRequest model."""
    request = SessionSearchRequest(
        query="AI safety",
        filters={"status": ["completed"]},
        sort="created_at:desc",
        limit=25,
        offset=10
    )
    
    assert request.query == "AI safety"
    assert request.limit == 25


# TraceEvent Tests

def test_reasoning_step_event():
    """Test ReasoningStepEvent model."""
    event = ReasoningStepEvent(
        session_id=uuid4(),
        sequence_number=1,
        prompt="What is AI safety?",
        response="AI safety is...",
        model="gpt-4",
        input_tokens=10,
        output_tokens=20,
        cost=Decimal("0.001")
    )
    
    assert event.event_type == "reasoning_step"
    assert event.prompt == "What is AI safety?"
    assert event.model == "gpt-4"
    assert event.input_tokens == 10
    assert event.temperature == 0.7  # default value


def test_reasoning_step_with_metadata():
    """Test ReasoningStepEvent with optional fields."""
    event = ReasoningStepEvent(
        session_id=uuid4(),
        sequence_number=1,
        prompt="Analyze this",
        response="Analysis result",
        model="gpt-4",
        temperature=0.9,
        max_tokens=2000,
        input_tokens=100,
        output_tokens=200,
        cost=Decimal("0.015"),
        reasoning_type="planning",
        chain_of_thought="First, I will...",
        entropy=0.85,
        confidence=0.92
    )
    
    assert event.reasoning_type == "planning"
    assert event.chain_of_thought == "First, I will..."
    assert event.entropy == 0.85
    assert event.confidence == 0.92


def test_tool_call_event():
    """Test ToolCallEvent model."""
    start = datetime.utcnow()
    event = ToolCallEvent(
        session_id=uuid4(),
        sequence_number=2,
        tool_name="web_search",
        tool_type="api",
        inputs={"query": "AI safety"},
        start_time=start
    )
    
    assert event.event_type == "tool_call"
    assert event.tool_name == "web_search"
    assert event.inputs["query"] == "AI safety"
    assert event.retry_count == 0


def test_tool_call_with_error():
    """Test ToolCallEvent with error information."""
    error = ErrorInfo(
        error_type="TimeoutError",
        message="Request timed out",
        recoverable=True,
        retry_attempted=True
    )
    
    event = ToolCallEvent(
        session_id=uuid4(),
        sequence_number=2,
        tool_name="database_query",
        tool_type="database",
        inputs={"query": "SELECT * FROM users"},
        start_time=datetime.utcnow(),
        error=error,
        stack_trace="Traceback..."
    )
    
    assert event.error is not None
    assert event.error.error_type == "TimeoutError"
    assert event.stack_trace == "Traceback..."


def test_memory_access_event():
    """Test MemoryAccessEvent model."""
    memory_items = [
        MemoryItem(
            content="Previous research on AI safety",
            relevance_score=0.95,
            metadata={"source": "paper_123"},
            timestamp=datetime.utcnow()
        )
    ]
    
    event = MemoryAccessEvent(
        session_id=uuid4(),
        sequence_number=3,
        query="previous research",
        memory_type="long_term",
        retrieval_method="semantic_search",
        num_results=1,
        results=memory_items
    )
    
    assert event.event_type == "memory_access"
    assert event.query == "previous research"
    assert event.num_results == 1
    assert len(event.results) == 1
    assert event.results[0].relevance_score == 0.95


def test_decision_point_event():
    """Test DecisionPointEvent model."""
    candidates = [
        DecisionCandidate(
            candidate_id="opt1",
            action="Search web",
            score=0.8,
            reasoning="Most relevant"
        ),
        DecisionCandidate(
            candidate_id="opt2",
            action="Query database",
            score=0.6,
            reasoning="Less relevant"
        )
    ]
    
    event = DecisionPointEvent(
        session_id=uuid4(),
        sequence_number=4,
        decision_type="action_selection",
        context="Need to find information",
        candidates=candidates,
        selected_candidate_id="opt1",
        reasoning="Web search has higher relevance"
    )
    
    assert event.event_type == "decision_point"
    assert event.decision_type == "action_selection"
    assert len(event.candidates) == 2
    assert event.selected_candidate_id == "opt1"


def test_planning_phase_event():
    """Test PlanningPhaseEvent model."""
    sub_tasks = [
        SubTask(
            task_id="task1",
            description="Research topic",
            dependencies=[],
            status="completed"
        ),
        SubTask(
            task_id="task2",
            description="Write summary",
            dependencies=["task1"],
            status="in_progress"
        )
    ]
    
    event = PlanningPhaseEvent(
        session_id=uuid4(),
        sequence_number=5,
        goal="Complete research project",
        sub_tasks=sub_tasks,
        planning_strategy="sequential"
    )
    
    assert event.event_type == "planning_phase"
    assert event.goal == "Complete research project"
    assert len(event.sub_tasks) == 2
    assert event.sub_tasks[1].dependencies == ["task1"]
    assert event.is_revision is False


def test_planning_phase_revision():
    """Test PlanningPhaseEvent with revision tracking."""
    event = PlanningPhaseEvent(
        session_id=uuid4(),
        sequence_number=6,
        goal="Revised goal",
        sub_tasks=[],
        planning_strategy="hierarchical",
        is_revision=True,
        previous_plan_id=uuid4(),
        revision_reason="Initial plan was too complex"
    )
    
    assert event.is_revision is True
    assert event.previous_plan_id is not None
    assert event.revision_reason == "Initial plan was too complex"


def test_custom_metric_event():
    """Test CustomMetricEvent model."""
    event = CustomMetricEvent(
        session_id=uuid4(),
        sequence_number=7,
        metric_name="response_quality",
        metric_value=0.95,
        metric_type="gauge",
        unit="score",
        tags={"model": "gpt-4", "task": "summarization"}
    )
    
    assert event.event_type == "custom_metric"
    assert event.metric_name == "response_quality"
    assert event.metric_value == 0.95
    assert event.tags["model"] == "gpt-4"


def test_annotation_event():
    """Test AnnotationEvent model."""
    event = AnnotationEvent(
        session_id=uuid4(),
        sequence_number=8,
        text="Important milestone reached",
        annotation_type="milestone",
        related_event_ids=[uuid4(), uuid4()]
    )
    
    assert event.event_type == "annotation"
    assert event.text == "Important milestone reached"
    assert event.annotation_type == "milestone"
    assert len(event.related_event_ids) == 2


def test_error_info():
    """Test ErrorInfo model."""
    error = ErrorInfo(
        error_type="ToolCallError",
        message="Connection timeout",
        recoverable=True,
        retry_attempted=True,
        context={"timeout_seconds": 30}
    )
    
    assert error.error_type == "ToolCallError"
    assert error.message == "Connection timeout"
    assert error.recoverable is True
    assert error.context["timeout_seconds"] == 30


def test_event_batch_request():
    """Test EventBatchRequest model."""
    request = EventBatchRequest(
        events=[
            {"event_type": "reasoning_step", "data": {}},
            {"event_type": "tool_call", "data": {}}
        ],
        compression="gzip"
    )
    
    assert len(request.events) == 2
    assert request.compression == "gzip"


def test_event_batch_response():
    """Test EventBatchResponse model."""
    response = EventBatchResponse(
        accepted_count=95,
        rejected_count=5,
        errors=[
            {"index": 0, "error": "Invalid schema"}
        ]
    )
    
    assert response.accepted_count == 95
    assert response.rejected_count == 5
    assert len(response.errors) == 1
    assert response.errors[0].index == 0
    assert response.errors[0].error == "Invalid schema"


def test_trace_event_parent_relationship():
    """Test TraceEvent parent-child relationship."""
    parent_event = ReasoningStepEvent(
        session_id=uuid4(),
        sequence_number=1,
        prompt="Parent step",
        response="Response",
        model="gpt-4",
        input_tokens=10,
        output_tokens=20,
        cost=Decimal("0.001")
    )
    
    child_event = ToolCallEvent(
        session_id=parent_event.session_id,
        sequence_number=2,
        parent_event_id=parent_event.event_id,
        tool_name="web_search",
        tool_type="api",
        inputs={"query": "test"},
        start_time=datetime.utcnow()
    )
    
    assert child_event.parent_event_id == parent_event.event_id
    assert child_event.session_id == parent_event.session_id


def test_json_serialization():
    """Test that models can be serialized to JSON."""
    session = Session(
        user_id="user_123",
        agent_type="langchain",
        goal="Test serialization"
    )
    
    # Test that model_dump works (Pydantic v2)
    json_data = session.model_dump()
    assert json_data["user_id"] == "user_123"
    assert json_data["agent_type"] == "langchain"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
