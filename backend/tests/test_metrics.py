"""Tests for analytics and metrics endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from services.auth import TokenData


class DummyConn:
    def __init__(self, fetchrow_return=None, fetch_return=None):
        self._fetchrow_return = fetchrow_return
        self._fetch_return = fetch_return or []

    async def fetchrow(self, *args, **kwargs):
        return self._fetchrow_return

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
    return TokenData(user_id=user_id, permissions=["metrics:read"], exp=datetime.utcnow() + timedelta(hours=1))


def test_get_aggregate_metrics_with_data(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    from main import create_app

    # Mock aggregation row
    agg_row = MagicMock()
    agg_row.__getitem__ = lambda self, key: {
        "total_sessions": 10,
        "completed_sessions": 8,
        "failed_sessions": 2,
        "avg_duration_ms": 1500.0,
        "median_duration_ms": 1200.0,
        "p95_duration_ms": 2500.0,
        "total_tokens_used": 5000,
        "avg_tokens_per_session": 500.0,
        "total_cost": 25.0,
        "avg_cost_per_session": 2.5,
        "total_reasoning_steps": 30,
        "avg_reasoning_steps_per_session": 3.0,
        "total_tool_calls": 20,
        "avg_tool_calls_per_session": 2.0,
        "error_count": 5
    }.get(key)
    
    conn = DummyConn(fetchrow_return=agg_row)
    pool = DummyPool(conn)

    with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
        import services.database as database
        database._pool = pool

        app = create_app()
        client = TestClient(app)

        resp = client.get(
            "/api/v1/metrics/aggregate?days=7",
            headers={"Authorization": "Bearer faketoken"}
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_sessions"] == 10
        assert data["completed_sessions"] == 8
        assert data["failed_sessions"] == 2
        assert data["success_rate"] == 0.8
        assert data["avg_duration_ms"] == 1500.0
        assert data["total_tokens_used"] == 5000
        assert data["total_cost"] == 25.0


def test_get_aggregate_metrics_no_data(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    from main import create_app

    # Mock empty aggregation
    agg_row = MagicMock()
    agg_row.__getitem__ = lambda self, key: {
        "total_sessions": None,
        "completed_sessions": None,
        "failed_sessions": None,
        "avg_duration_ms": None,
        "median_duration_ms": None,
        "p95_duration_ms": None,
        "total_tokens_used": None,
        "avg_tokens_per_session": None,
        "total_cost": None,
        "avg_cost_per_session": None,
        "total_reasoning_steps": None,
        "avg_reasoning_steps_per_session": None,
        "total_tool_calls": None,
        "avg_tool_calls_per_session": None,
        "error_count": None
    }.get(key)
    
    conn = DummyConn(fetchrow_return=agg_row)
    pool = DummyPool(conn)

    with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
        import services.database as database
        database._pool = pool

        app = create_app()
        client = TestClient(app)

        resp = client.get(
            "/api/v1/metrics/aggregate?days=7",
            headers={"Authorization": "Bearer faketoken"}
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_sessions"] == 0
        assert data["success_rate"] == 0.0


def test_get_timeseries_metrics_cost(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    from main import create_app

    # Mock time-series data points
    now = datetime.utcnow()
    hour_ago = now - timedelta(hours=1)
    
    point1 = MagicMock()
    point1.__getitem__ = lambda self, key: {
        "bucket": hour_ago,
        "value": 5.0
    }.get(key)
    
    point2 = MagicMock()
    point2.__getitem__ = lambda self, key: {
        "bucket": now,
        "value": 3.0
    }.get(key)
    
    conn = DummyConn(fetch_return=[point1, point2])
    pool = DummyPool(conn)

    with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
        import services.database as database
        database._pool = pool

        app = create_app()
        client = TestClient(app)

        resp = client.get(
            "/api/v1/metrics/timeseries?metric=cost&days=7&bucket_hours=24",
            headers={"Authorization": "Bearer faketoken"}
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["metric_name"] == "cost"
        assert len(data["data_points"]) == 2
        assert data["data_points"][0]["value"] == 5.0
        assert data["data_points"][1]["value"] == 3.0


def test_get_timeseries_metrics_success_rate(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    from main import create_app

    # Mock success rate data points
    now = datetime.utcnow()
    hour_ago = now - timedelta(hours=1)
    
    point1 = MagicMock()
    point1.__getitem__ = lambda self, key: {
        "bucket": hour_ago,
        "value": 0.8
    }.get(key)
    
    point2 = MagicMock()
    point2.__getitem__ = lambda self, key: {
        "bucket": now,
        "value": 0.9
    }.get(key)
    
    conn = DummyConn(fetch_return=[point1, point2])
    pool = DummyPool(conn)

    with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
        import services.database as database
        database._pool = pool

        app = create_app()
        client = TestClient(app)

        resp = client.get(
            "/api/v1/metrics/timeseries?metric=success_rate&days=7",
            headers={"Authorization": "Bearer faketoken"}
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["metric_name"] == "success_rate"
        assert len(data["data_points"]) == 2
        assert data["data_points"][0]["value"] == 0.8
