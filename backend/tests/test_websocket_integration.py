"""Integration-style tests for FastAPI WebSocket gateway behavior."""

from datetime import datetime
from uuid import uuid4
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.routes import websocket as websocket_route
from services.event_hub import EventHub


class DummyConn:
    def __init__(self, rows=None, owned=True):
        self.rows = rows or []
        self.owned = owned

    async def fetchval(self, *args, **kwargs):
        return 1 if self.owned else None

    async def fetch(self, *args, **kwargs):
        return self.rows


class DummyAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class DummyPool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return DummyAcquire(self.conn)


def make_app() -> FastAPI:
    app = FastAPI()
    app.state.event_hub = EventHub(batch_window_ms=0)
    app.state.ws_heartbeat_interval = 0.01
    app.include_router(websocket_route.router, prefix="/api/v1")
    return app


def make_row(session_id, sequence_number=1):
    return {
        "event_id": uuid4(),
        "session_id": session_id,
        "event_type": "tool_call",
        "timestamp": datetime.utcnow(),
        "sequence_number": sequence_number,
        "parent_event_id": None,
        "duration_ms": 1,
        "status": "completed",
        "event_data": {"tool_name": "search"},
    }


def test_websocket_rejects_missing_token():
    app = make_app()
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/ws"):
            pass

    assert exc.value.code == 1008


def test_websocket_subscription_snapshot_and_event_delivery():
    app = make_app()
    session_id = uuid4()
    pool = DummyPool(DummyConn(rows=[make_row(session_id, sequence_number=1)]))

    async def authenticate(_token):
        return "user-1"

    async def get_pool():
        return pool

    with patch.object(websocket_route, "_authenticate", authenticate), \
         patch.object(websocket_route, "get_db_pool", get_pool), \
         TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws?token=ok") as ws:
            ws.send_json({"type": "subscribe", "session_id": str(session_id)})
            snapshot = ws.receive_json()

            assert snapshot["type"] == "snapshot"
            assert snapshot["events"][0]["sequence_number"] == 1

            client.portal.call(
                app.state.event_hub.broadcast,
                str(session_id),
                {"session_id": str(session_id), "sequence_number": 2, "event_type": "annotation"},
            )
            event = ws.receive_json()

            assert event["type"] == "event"
            assert event["event"]["sequence_number"] == 2


def test_websocket_heartbeat_ping():
    app = make_app()
    pool = DummyPool(DummyConn())

    async def authenticate(_token):
        return "user-1"

    async def get_pool():
        return pool

    with patch.object(websocket_route, "_authenticate", authenticate), \
         patch.object(websocket_route, "get_db_pool", get_pool), \
         TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws?token=ok") as ws:
            message = ws.receive_json()
            assert message == {"type": "ping"}
            ws.send_json({"type": "pong"})


def test_websocket_resume_uses_last_sequence_number():
    app = make_app()
    session_id = uuid4()
    pool = DummyPool(DummyConn(rows=[make_row(session_id, sequence_number=3)]))

    async def authenticate(_token):
        return "user-1"

    async def get_pool():
        return pool

    with patch.object(websocket_route, "_authenticate", authenticate), \
         patch.object(websocket_route, "get_db_pool", get_pool), \
         TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws?token=ok") as ws:
            ws.send_json({
                "type": "subscribe",
                "session_id": str(session_id),
                "last_sequence_number": 2,
            })
            snapshot = ws.receive_json()

            assert snapshot["type"] == "snapshot"
            assert snapshot["events"][0]["sequence_number"] == 3
