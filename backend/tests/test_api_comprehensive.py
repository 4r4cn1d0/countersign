"""Comprehensive unit tests for API endpoints covering validation, auth, and error handling."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from uuid import uuid4

from services.auth import TokenData


class DummyConn:
    def __init__(self, fetchrow_return=None, fetch_return=None, fetchval_return=None, execute_side_effect=None):
        self._fetchrow_return = fetchrow_return
        self._fetch_return = fetch_return or []
        self._fetchval_return = fetchval_return
        self._execute_side_effect = execute_side_effect

    async def execute(self, *args, **kwargs):
        if self._execute_side_effect:
            raise self._execute_side_effect
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
def mock_services():
    with patch('services.database.init_db'), \
         patch('services.redis_service.init_redis'), \
         patch('services.database.close_db'), \
         patch('services.redis_service.close_redis'):
        yield


def make_token(user_id: str = "test_user", permissions: list = None) -> TokenData:
    if permissions is None:
        permissions = ["sessions:read", "sessions:write", "metrics:read"]
    return TokenData(user_id=user_id, permissions=permissions, exp=datetime.utcnow() + timedelta(hours=1))


class TestSessionValidationAndAuth:
    """Test session endpoints for validation and authentication."""

    def test_create_session_missing_authentication(self, mock_services):
        from main import create_app

        app = create_app()
        client = TestClient(app)

        payload = {"goal": "Test goal", "agent_type": "langchain"}
        resp = client.post("/api/v1/sessions", json=payload)

        assert resp.status_code == 403
        resp_text = resp.text.lower()
        assert "not authenticated" in resp_text or "credentials" in resp_text

    def test_create_session_invalid_token(self, mock_services):
        from main import create_app

        with patch('services.auth.AuthService.verify_jwt_token', return_value=None):
            app = create_app()
            client = TestClient(app)

            payload = {"goal": "Test goal", "agent_type": "langchain"}
            resp = client.post(
                "/api/v1/sessions",
                json=payload,
                headers={"Authorization": "Bearer invalid_token"}
            )

            assert resp.status_code == 401

    def test_create_session_missing_required_fields(self, mock_services):
        from main import create_app

        conn = DummyConn()
        pool = DummyPool(conn)

        with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
            import services.database as database
            database._pool = pool

            app = create_app()
            client = TestClient(app)

            # Missing 'goal' field
            payload = {"agent_type": "langchain"}
            resp = client.post(
                "/api/v1/sessions",
                json=payload,
                headers={"Authorization": "Bearer faketoken"}
            )

            assert resp.status_code == 422

    def test_get_session_unauthorized_access(self, mock_services):
        from main import create_app

        session_id = uuid4()
        
        # Session belongs to different user
        session_row = None
        conn = DummyConn(fetchrow_return=session_row)
        pool = DummyPool(conn)

        with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token("different_user")):
            import services.database as database
            database._pool = pool

            app = create_app()
            client = TestClient(app)

            resp = client.get(
                f"/api/v1/sessions/{session_id}",
                headers={"Authorization": "Bearer faketoken"}
            )

            assert resp.status_code == 404
            assert "not found" in resp.text.lower()


class TestEventValidationAndErrorHandling:
    """Test event endpoints for validation and error handling."""

    def test_append_events_missing_events_list(self, mock_services):
        from main import create_app

        session_id = uuid4()
        session_row = {"session_id": session_id}
        conn = DummyConn(fetchrow_return=session_row)
        pool = DummyPool(conn)

        with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
            import services.database as database
            database._pool = pool

            app = create_app()
            client = TestClient(app)

            # Missing 'events' field
            payload = {}
            resp = client.post(
                f"/api/v1/sessions/{session_id}/events",
                json=payload,
                headers={"Authorization": "Bearer faketoken"}
            )

            assert resp.status_code == 422

    def test_append_events_invalid_event_type(self, mock_services):
        from main import create_app

        session_id = uuid4()
        session_row = {"session_id": session_id}
        conn = DummyConn(fetchrow_return=session_row)
        pool = DummyPool(conn)

        with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
            import services.database as database
            database._pool = pool

            with patch('api.routes.events.MessageQueueProducer'):
                app = create_app()
                client = TestClient(app)

                payload = {
                    "events": [
                        {
                            "session_id": str(session_id),
                            "event_type": "invalid_type",
                            "sequence_number": 1
                        }
                    ]
                }
                resp = client.post(
                    f"/api/v1/sessions/{session_id}/events",
                    json=payload,
                    headers={"Authorization": "Bearer faketoken"}
                )

                assert resp.status_code == 202
                data = resp.json()
                assert data["rejected_count"] == 1
                assert data["accepted_count"] == 0

    def test_batch_upload_events_invalid_compression(self, mock_services):
        from main import create_app

        session_id = uuid4()
        session_row = {"session_id": session_id}
        conn = DummyConn(fetchrow_return=session_row)
        pool = DummyPool(conn)

        with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
            import services.database as database
            database._pool = pool

            app = create_app()
            client = TestClient(app)

            payload = {
                "events": [
                    {
                        "session_id": str(session_id),
                        "event_type": "reasoning_step",
                        "sequence_number": 1,
                        "prompt": "test",
                        "response": "test",
                        "model": "gpt",
                        "temperature": 0.7,
                        "max_tokens": 100,
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "cost": 0.01
                    }
                ],
                "compression": "invalid_compression"
            }
            resp = client.post(
                f"/api/v1/sessions/{session_id}/events/batch",
                json=payload,
                headers={"Authorization": "Bearer faketoken"}
            )

            assert resp.status_code == 422
            assert "compression" in resp.text.lower()

    def test_append_events_session_id_mismatch(self, mock_services):
        from main import create_app

        session_id = uuid4()
        different_session_id = uuid4()
        session_row = {"session_id": session_id}
        conn = DummyConn(fetchrow_return=session_row)
        pool = DummyPool(conn)

        with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
            import services.database as database
            database._pool = pool

            with patch('api.routes.events.MessageQueueProducer'):
                app = create_app()
                client = TestClient(app)

                payload = {
                    "events": [
                        {
                            "session_id": str(different_session_id),
                            "event_type": "reasoning_step",
                            "sequence_number": 1,
                            "prompt": "test",
                            "response": "test",
                            "model": "gpt",
                            "temperature": 0.7,
                            "max_tokens": 100,
                            "input_tokens": 10,
                            "output_tokens": 5,
                            "cost": 0.01
                        }
                    ]
                }
                resp = client.post(
                    f"/api/v1/sessions/{session_id}/events",
                    json=payload,
                    headers={"Authorization": "Bearer faketoken"}
                )

                assert resp.status_code == 202
                data = resp.json()
                assert data["rejected_count"] == 1


class TestTraceRetrievalAuthorization:
    """Test trace retrieval endpoints for authorization."""

    def test_get_trace_unauthorized(self, mock_services):
        from main import create_app

        session_id = uuid4()
        
        # Session not found for this user
        conn = DummyConn(fetchrow_return=None)
        pool = DummyPool(conn)

        with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
            import services.database as database
            database._pool = pool

            app = create_app()
            client = TestClient(app)

            resp = client.get(
                f"/api/v1/sessions/{session_id}/trace",
                headers={"Authorization": "Bearer faketoken"}
            )

            assert resp.status_code == 404

    def test_get_graph_no_events(self, mock_services):
        from main import create_app

        session_id = uuid4()
        session_row = {"session_id": session_id}
        conn = DummyConn(fetchrow_return=session_row, fetch_return=[])
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
            assert data["nodes"] == []
            assert data["edges"] == []


class TestMetricsAuthorization:
    """Test metrics endpoints for proper scoping."""

    def test_aggregate_metrics_user_scoped(self, mock_services):
        from main import create_app

        agg_row = MagicMock()
        agg_row.__getitem__ = lambda self, key: {
            "total_sessions": 5,
            "completed_sessions": 4,
            "failed_sessions": 1,
            "avg_duration_ms": 1000.0,
            "median_duration_ms": 950.0,
            "p95_duration_ms": 2000.0,
            "total_tokens_used": 2500,
            "avg_tokens_per_session": 500.0,
            "total_cost": 10.0,
            "avg_cost_per_session": 2.0,
            "total_reasoning_steps": 15,
            "avg_reasoning_steps_per_session": 3.0,
            "total_tool_calls": 10,
            "avg_tool_calls_per_session": 2.0,
            "error_count": 2
        }.get(key)
        
        conn = DummyConn(fetchrow_return=agg_row)
        pool = DummyPool(conn)

        with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token("user_123")):
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
            assert data["total_sessions"] == 5

    def test_timeseries_metrics_invalid_metric(self, mock_services):
        from main import create_app

        conn = DummyConn()
        pool = DummyPool(conn)

        with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
            import services.database as database
            database._pool = pool

            app = create_app()
            client = TestClient(app)

            resp = client.get(
                "/api/v1/metrics/timeseries?metric=invalid_metric",
                headers={"Authorization": "Bearer faketoken"}
            )

            assert resp.status_code == 422


class TestPaginationValidation:
    """Test pagination parameter validation."""

    def test_trace_retrieval_invalid_page(self, mock_services):
        from main import create_app

        session_id = uuid4()
        session_row = {"session_id": session_id}
        conn = DummyConn(fetchrow_return=session_row)
        pool = DummyPool(conn)

        with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
            import services.database as database
            database._pool = pool

            app = create_app()
            client = TestClient(app)

            resp = client.get(
                f"/api/v1/sessions/{session_id}/trace?page=0&page_size=50",
                headers={"Authorization": "Bearer faketoken"}
            )

            assert resp.status_code == 422

    def test_trace_retrieval_page_size_too_large(self, mock_services):
        from main import create_app

        session_id = uuid4()
        session_row = {"session_id": session_id}
        conn = DummyConn(fetchrow_return=session_row)
        pool = DummyPool(conn)

        with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
            import services.database as database
            database._pool = pool

            app = create_app()
            client = TestClient(app)

            resp = client.get(
                f"/api/v1/sessions/{session_id}/trace?page=1&page_size=1000",
                headers={"Authorization": "Bearer faketoken"}
            )

            assert resp.status_code == 422


class TestQueryParameterValidation:
    """Test query parameter validation."""

    def test_aggregate_metrics_invalid_days(self, mock_services):
        from main import create_app

        conn = DummyConn()
        pool = DummyPool(conn)

        with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
            import services.database as database
            database._pool = pool

            app = create_app()
            client = TestClient(app)

            resp = client.get(
                "/api/v1/metrics/aggregate?days=0",
                headers={"Authorization": "Bearer faketoken"}
            )

            assert resp.status_code == 422

    def test_aggregate_metrics_days_exceeds_max(self, mock_services):
        from main import create_app

        conn = DummyConn()
        pool = DummyPool(conn)

        with patch('services.auth.AuthService.verify_jwt_token', return_value=make_token()):
            import services.database as database
            database._pool = pool

            app = create_app()
            client = TestClient(app)

            resp = client.get(
                "/api/v1/metrics/aggregate?days=400",
                headers={"Authorization": "Bearer faketoken"}
            )

            assert resp.status_code == 422
