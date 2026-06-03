"""Tests for reconnecting WebSocket client helper."""

import json

import pytest

from services.websocket_client import ReconnectPolicy, ReconnectingWebSocketClient


class FakeConnection:
    def __init__(self, messages=None, fail_enter=False):
        self.messages = list(messages or [])
        self.fail_enter = fail_enter
        self.sent = []

    async def __aenter__(self):
        if self.fail_enter:
            raise ConnectionError("offline")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)

    async def send(self, payload):
        self.sent.append(json.loads(payload))


def test_reconnect_policy_uses_exponential_backoff_with_cap():
    policy = ReconnectPolicy(initial_delay_seconds=1, max_delay_seconds=5, multiplier=2)

    assert [policy.delay_for_attempt(i) for i in range(1, 5)] == [1, 2, 4, 5]


@pytest.mark.asyncio
async def test_client_reconnects_with_backoff_and_resumes(monkeypatch):
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("services.websocket_client.asyncio.sleep", fake_sleep)

    connections = [
        FakeConnection(fail_enter=True),
        FakeConnection(messages=[
            json.dumps({"type": "snapshot", "events": [{"sequence_number": 2}]}),
            json.dumps({"type": "event", "event": {"sequence_number": 3, "event_type": "tool_call"}}),
        ]),
    ]

    def connect_factory(_uri):
        return connections.pop(0)

    events = []
    snapshots = []
    client = ReconnectingWebSocketClient(
        "ws://test/ws",
        token="token",
        session_id="session-1",
        reconnect_policy=ReconnectPolicy(initial_delay_seconds=0.5, max_attempts=2),
        connect_factory=connect_factory,
    )

    async def on_event(event):
        events.append(event)
        client.stop()

    async def on_snapshot(items):
        snapshots.append(items)

    await client.run(on_event, on_snapshot)

    assert sleeps == [0.5]
    assert snapshots == [[{"sequence_number": 2}]]
    assert events == [{"sequence_number": 3, "event_type": "tool_call"}]
    assert client.last_sequence_number == 3


@pytest.mark.asyncio
async def test_client_responds_to_ping_and_handles_batches():
    connection = FakeConnection(messages=[
        json.dumps({"type": "ping"}),
        json.dumps({
            "type": "events",
            "events": [
                {"event": {"sequence_number": 1}},
                {"event": {"sequence_number": 2}},
            ],
        }),
    ])
    client = ReconnectingWebSocketClient(
        "ws://test/ws",
        token="token",
        session_id="session-1",
        connect_factory=lambda _uri: connection,
    )
    events = []

    async def on_event(event):
        events.append(event)
        if len(events) == 2:
            client.stop()

    await client.run(on_event)

    assert connection.sent[0] == {"type": "subscribe", "session_id": "session-1"}
    assert connection.sent[1] == {"type": "pong"}
    assert events == [{"sequence_number": 1}, {"sequence_number": 2}]
