"""Tests for WebSocket event hub."""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock

from services.event_hub import EventHub


@pytest.mark.asyncio
async def test_broadcast_to_subscriber():
    hub = EventHub()
    ws = AsyncMock()
    await hub.subscribe("session-1", ws)
    await hub.broadcast("session-1", {"event_type": "tool_call"})
    await hub.wait_idle(ws)
    ws.send_text.assert_called_once()
    payload = ws.send_text.call_args[0][0]
    assert "tool_call" in payload
    await hub.unsubscribe_all(ws)


@pytest.mark.asyncio
async def test_unsubscribe_all():
    hub = EventHub()
    ws = AsyncMock()
    await hub.subscribe("session-1", ws)
    await hub.unsubscribe_all(ws)
    await hub.broadcast("session-1", {"event_type": "x"})
    ws.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_backpressure_drops_oldest_pending_message():
    hub = EventHub(client_buffer_size=1, batch_window_ms=0)
    ws = AsyncMock()
    release_first_send = asyncio.Event()
    sent = []

    async def send_text(message):
        sent.append(json.loads(message)["event"]["sequence_number"])
        if len(sent) == 1:
            await release_first_send.wait()

    ws.send_text.side_effect = send_text

    await hub.subscribe("session-1", ws)
    await hub.broadcast("session-1", {"sequence_number": 1})
    await asyncio.sleep(0)
    await hub.broadcast("session-1", {"sequence_number": 2})
    await hub.broadcast("session-1", {"sequence_number": 3})

    assert hub.dropped_count(ws) == 1

    release_first_send.set()
    await hub.wait_idle(ws)

    assert sent == [1, 3]
    await hub.unsubscribe_all(ws)


@pytest.mark.asyncio
async def test_send_failure_removes_dead_socket():
    hub = EventHub(batch_window_ms=0)
    ws = AsyncMock()
    ws.send_text.side_effect = RuntimeError("disconnected")

    await hub.subscribe("session-1", ws)
    await hub.broadcast("session-1", {"event_type": "tool_call"})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert ws not in hub._clients


@pytest.mark.asyncio
async def test_broadcast_batches_queued_messages():
    hub = EventHub(batch_window_ms=25, batch_max_size=10)
    ws = AsyncMock()

    await hub.subscribe("session-1", ws)
    await hub.broadcast("session-1", {"sequence_number": 1})
    await hub.broadcast("session-1", {"sequence_number": 2})
    await hub.wait_idle(ws)

    payload = json.loads(ws.send_text.call_args.args[0])
    assert payload["type"] == "events"
    assert [item["event"]["sequence_number"] for item in payload["events"]] == [1, 2]
    await hub.unsubscribe_all(ws)


@pytest.mark.asyncio
async def test_close_sends_shutdown_notice_and_closes_socket():
    hub = EventHub()
    ws = AsyncMock()

    await hub.subscribe("session-1", ws)
    await hub.close("test_shutdown")

    payload = json.loads(ws.send_text.call_args.args[0])
    assert payload == {"type": "closing", "reason": "test_shutdown"}
    ws.close.assert_called_once_with(code=1001, reason="test_shutdown")
    assert ws not in hub._clients
