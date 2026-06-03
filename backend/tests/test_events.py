"""Tests for trace event ingestion endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta
from uuid import uuid4

from services.auth import TokenData


class DummyConn:
    def __init__(self, fetchrow_return=None):
        self._fetchrow_return = fetchrow_return

    async def execute(self, *args, **kwargs):
        return None

    async def fetchrow(self, *args, **kwargs):
        return self._fetchrow_return

    async def fetchval(self, *args, **kwargs):
        return 1

    async def fetch(self, *args, **kwargs):
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


def make_reasoning_event(session_id):
    return {
        "session_id": str(session_id),
        "event_type": "reasoning_step",
        "sequence_number": 1,
        "prompt": "Test prompt",
        "response": "Test response",
        "model": "gpt-test",
        "temperature": 0.7,
        "max_tokens": 100,
        "input_tokens": 10,
        "output_tokens": 12,
        "cost": 1.5
    }


def test_append_events_success(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    from main import create_app

    session_id = uuid4()
    row = {"session_id": session_id}
    conn = DummyConn(fetchrow_return=row)
    pool = DummyPool(conn)

    with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
        import services.database as database
        database._pool = pool

        with patch('api.routes.events.MessageQueueProducer') as mock_producer_cls:
            mock_producer = AsyncMock()
            mock_producer.publish_batch = AsyncMock(return_value=["1-0"])
            mock_producer_cls.return_value = mock_producer

            app = create_app()
            client = TestClient(app)

            payload = {"events": [make_reasoning_event(session_id)]}
            resp = client.post(
                f"/api/v1/sessions/{session_id}/events",
                json=payload,
                headers={"Authorization": "Bearer faketoken"}
            )

            assert resp.status_code == 202
            data = resp.json()
            assert data["accepted_count"] == 1
            assert data["rejected_count"] == 0
            assert data["errors"] == []
            mock_producer.publish_batch.assert_awaited_once()


def test_batch_upload_events_success(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    from main import create_app

    session_id = uuid4()
    row = {"session_id": session_id}
    conn = DummyConn(fetchrow_return=row)
    pool = DummyPool(conn)

    with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
        import services.database as database
        database._pool = pool

        with patch('api.routes.events.MessageQueueProducer') as mock_producer_cls:
            mock_producer = AsyncMock()
            mock_producer.publish_batch = AsyncMock(return_value=["1-0", "1-1"])
            mock_producer_cls.return_value = mock_producer

            app = create_app()
            client = TestClient(app)

            payload = {
                "events": [
                    make_reasoning_event(session_id),
                    make_reasoning_event(session_id)
                ],
                "compression": "gzip"
            }
            resp = client.post(
                f"/api/v1/sessions/{session_id}/events/batch",
                json=payload,
                headers={"Authorization": "Bearer faketoken"}
            )

            assert resp.status_code == 202
            data = resp.json()
            assert data["accepted_count"] == 2
            assert data["rejected_count"] == 0
            assert data["errors"] == []
            mock_producer.publish_batch.assert_awaited_once()


def test_batch_upload_events_invalid_compression(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    from main import create_app

    session_id = uuid4()
    row = {"session_id": session_id}
    conn = DummyConn(fetchrow_return=row)
    pool = DummyPool(conn)

    with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
        import services.database as database
        database._pool = pool

        app = create_app()
        client = TestClient(app)

        payload = {
            "events": [make_reasoning_event(session_id)],
            "compression": "unsupported"
        }
        resp = client.post(
            f"/api/v1/sessions/{session_id}/events/batch",
            json=payload,
            headers={"Authorization": "Bearer faketoken"}
        )

        assert resp.status_code == 422
        assert "Unsupported compression type" in resp.text
