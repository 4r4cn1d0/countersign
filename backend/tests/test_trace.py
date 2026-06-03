"""Tests for trace retrieval endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from uuid import uuid4

from services.auth import TokenData


class DummyConn:
    def __init__(self, fetchrow_return=None, fetch_return=None, fetchval_return=None):
        self._fetchrow_return = fetchrow_return
        self._fetch_return = fetch_return or []
        self._fetchval_return = fetchval_return

    async def execute(self, *args, **kwargs):
        return None

    async def fetchrow(self, *args, **kwargs):
        return self._fetchrow_return

    async def fetchval(self, *args, **kwargs):
        return self._fetchval_return

    async def fetch(self, *args, **kwargs):
        return self._fetch_return


class DummyAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class DummyPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return DummyAcquire(self._conn)


@pytest.fixture
def mock_db_init():
    with patch('services.database.init_db'):
        yield


@pytest.fixture
def mock_redis_init():
    with patch('services.redis_service.init_redis'):
        yield


@pytest.fixture
def mock_db_close():
    with patch('services.database.close_db'):
        yield


@pytest.fixture
def mock_redis_close():
    with patch('services.redis_service.close_redis'):
        yield


def make_token(user_id: str = "test_user") -> TokenData:
    return TokenData(user_id=user_id, permissions=["sessions:read"], exp=datetime.utcnow() + timedelta(hours=1))


def test_get_session_trace_success(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    from main import create_app

    session_id = uuid4()
    
    # Mock session exists
    session_row = {"session_id": session_id}
    conn = DummyConn(fetchrow_return=session_row, fetchval_return=2)
    
    # Mock events returned
    event1 = MagicMock()
    event1.__getitem__ = lambda self, key: {
        "event_id": uuid4(),
        "session_id": session_id,
        "event_type": "reasoning_step",
        "timestamp": datetime.utcnow(),
        "sequence_number": 1,
        "duration_ms": 100,
        "status": "completed",
        "event_data": {"model": "gpt-test"}
    }.get(key)
    
    event2 = MagicMock()
    event2.__getitem__ = lambda self, key: {
        "event_id": uuid4(),
        "session_id": session_id,
        "event_type": "tool_call",
        "timestamp": datetime.utcnow(),
        "sequence_number": 2,
        "duration_ms": 50,
        "status": "completed",
        "event_data": {"tool_name": "search"}
    }.get(key)
    
    conn._fetch_return = [event1, event2]
    pool = DummyPool(conn)

    with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
        import services.database as database
        database._pool = pool

        app = create_app()
        client = TestClient(app)

        resp = client.get(
            f"/api/v1/sessions/{session_id}/trace?page=1&page_size=50",
            headers={"Authorization": "Bearer faketoken"}
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == str(session_id)
        assert data["total_events"] == 2
        assert len(data["events"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert data["has_more"] == False


def test_get_execution_graph_success(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    from main import create_app

    session_id = uuid4()
    parent_event_id = uuid4()
    child_event_id = uuid4()
    
    session_row = {"session_id": session_id}
    conn = DummyConn(fetchrow_return=session_row)
    
    # Mock events with parent-child relationship
    parent_event = MagicMock()
    parent_event.__getitem__ = lambda self, key: {
        "event_id": parent_event_id,
        "event_type": "reasoning_step",
        "timestamp": datetime.utcnow(),
        "sequence_number": 1,
        "duration_ms": 100,
        "status": "completed",
        "parent_event_id": None,
        "event_data": {"model": "gpt-test"}
    }.get(key)
    
    child_event = MagicMock()
    child_event.__getitem__ = lambda self, key: {
        "event_id": child_event_id,
        "event_type": "tool_call",
        "timestamp": datetime.utcnow(),
        "sequence_number": 2,
        "duration_ms": 50,
        "status": "completed",
        "parent_event_id": parent_event_id,
        "event_data": {"tool_name": "search"}
    }.get(key)
    
    conn._fetch_return = [parent_event, child_event]
    pool = DummyPool(conn)

    with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
        import services.database as database
        database._pool = pool

        app = create_app()
        client = TestClient(app)

        resp = client.get(
            f"/api/v1/sessions/{session_id}/graph",
            headers={"Authorization": "Bearer faketoken"}
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == str(session_id)
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        assert data["edges"][0]["source_event_id"] == str(parent_event_id)
        assert data["edges"][0]["target_event_id"] == str(child_event_id)


def test_get_session_metrics_success(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    from main import create_app

    session_id = uuid4()
    
    session_row = MagicMock()
    session_row.__getitem__ = lambda self, key: {
        "session_id": session_id,
        "goal": "Test goal",
        "status": "completed",
        "created_at": datetime.utcnow(),
        "completed_at": datetime.utcnow(),
        "duration_ms": 1000,
        "total_reasoning_steps": 3,
        "total_tool_calls": 2,
        "total_memory_accesses": 1,
        "total_tokens": 100,
        "total_cost": 0.5,
        "error_count": 0
    }.get(key)
    
    conn = DummyConn(fetchrow_return=session_row)
    
    # Mock event type counts
    event_counts = [
        MagicMock(spec=dict, **{"__getitem__": lambda s, k: {"reasoning_step": 3, "tool_call": 2, "memory_access": 1}[k] if k in {"reasoning_step", "tool_call", "memory_access"} else None}),
    ]
    conn._fetch_return = event_counts
    pool = DummyPool(conn)

    with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
        import services.database as database
        database._pool = pool

        app = create_app()
        client = TestClient(app)

        resp = client.get(
            f"/api/v1/sessions/{session_id}/metrics",
            headers={"Authorization": "Bearer faketoken"}
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == str(session_id)
        assert data["goal"] == "Test goal"
        assert data["status"] == "completed"
        assert data["total_tokens"] == 100
        assert data["total_cost"] == 0.5
