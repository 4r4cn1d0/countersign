"""Tests for session creation and retrieval endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from datetime import datetime, timedelta

from services.auth import TokenData


class DummyConn:
    def __init__(self, fetchrow_return=None):
        self._fetchrow_return = fetchrow_return
        self.fetch_calls = []
        self.fetchval_calls = []

    async def execute(self, *args, **kwargs):
        return None

    async def fetchrow(self, *args, **kwargs):
        return self._fetchrow_return

    async def fetchval(self, *args, **kwargs):
        self.fetchval_calls.append((args, kwargs))
        return 1

    async def fetch(self, *args, **kwargs):
        self.fetch_calls.append((args, kwargs))
        return []


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
    with patch('services.database.init_db') as m:
        yield m


@pytest.fixture
def mock_redis_init():
    with patch('services.redis_service.init_redis') as m:
        yield m


@pytest.fixture
def mock_db_close():
    with patch('services.database.close_db') as m:
        yield m


@pytest.fixture
def mock_redis_close():
    with patch('services.redis_service.close_redis') as m:
        yield m


def make_token(user_id: str = "test_user") -> TokenData:
    return TokenData(user_id=user_id, permissions=["sessions:write"], exp=datetime.utcnow() + timedelta(hours=1))


def test_create_session(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    from main import create_app

    # Prepare dummy DB pool
    conn = DummyConn()
    pool = DummyPool(conn)

    # Patch JWT verification and set the DB pool
    with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
        import services.database as database
        database._pool = pool

        app = create_app()
        client = TestClient(app)

        payload = {"goal": "Test goal", "agent_type": "langchain", "tags": ["test"]}
        resp = client.post("/api/v1/sessions", json=payload, headers={"Authorization": "Bearer faketoken"})

        assert resp.status_code == 201
        data = resp.json()
        assert data["goal"] == "Test goal"
        assert data["agent_type"] == "langchain"
        assert data["user_id"] == "test_user"


def test_get_session(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    from main import create_app
    from uuid import uuid4

    # Prepare dummy row
    session_id = uuid4()
    row = {
        "session_id": session_id,
        "user_id": "test_user",
        "agent_type": "langchain",
        "goal": "Test goal",
        "status": "running",
        "created_at": datetime.utcnow(),
        "completed_at": None,
        "duration_ms": None,
        "total_reasoning_steps": 0,
        "total_tool_calls": 0,
        "total_memory_accesses": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
        "error_count": 0,
        "metadata": None,
        "tags": ["test"],
        "coordination_id": None
    }

    conn = DummyConn(fetchrow_return=row)
    pool = DummyPool(conn)

    with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
        import services.database as database
        database._pool = pool

        app = create_app()
        client = TestClient(app)

        resp = client.get(f"/api/v1/sessions/{session_id}", headers={"Authorization": "Bearer faketoken"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == str(session_id)
        assert data["user_id"] == "test_user"
        assert data["goal"] == "Test goal"


def test_search_sessions_applies_duration_range_filter(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    from main import create_app

    conn = DummyConn()
    pool = DummyPool(conn)

    with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
        import services.database as database
        database._pool = pool

        app = create_app()
        client = TestClient(app)

        resp = client.post(
            "/api/v1/sessions/search",
            json={
                "filters": {
                    "duration_range": {
                        "min": 1000,
                        "max": 5000
                    }
                },
                "limit": 10,
                "offset": 0
            },
            headers={"Authorization": "Bearer faketoken"},
        )

    assert resp.status_code == 200
    assert conn.fetchval_calls
    count_query_args, _ = conn.fetchval_calls[0]
    count_query = count_query_args[0]
    assert "duration_ms >= $2" in count_query
    assert "duration_ms <= $3" in count_query
    assert count_query_args[1:4] == ("test_user", 1000, 5000)
