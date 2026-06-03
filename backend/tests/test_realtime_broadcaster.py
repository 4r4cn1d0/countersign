"""Tests for Redis-backed real-time WebSocket broadcasting."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from services.realtime_broadcaster import (
    ProcessedEventBroadcaster,
    ProcessedEventPublisher,
)


@pytest.mark.asyncio
async def test_processed_event_publisher_writes_to_processed_stream():
    redis = AsyncMock()
    redis.xadd = AsyncMock(return_value=b"1-0")
    publisher = ProcessedEventPublisher(stream_name="processed")

    with patch("services.realtime_broadcaster.get_redis_client", return_value=redis):
        message_id = await publisher.publish({
            "session_id": "session-1",
            "event_type": "tool_call",
        })

    assert message_id == "1-0"
    redis.xadd.assert_called_once()
    stream_name, payload = redis.xadd.call_args.args
    assert stream_name == "processed"
    assert payload["session_id"] == "session-1"
    assert json.loads(payload["event"])["event_type"] == "tool_call"


@pytest.mark.asyncio
async def test_processed_event_broadcaster_consumes_stream_and_fans_out():
    redis = AsyncMock()
    redis.xgroup_create = AsyncMock()
    redis.xack = AsyncMock()
    redis.xreadgroup = AsyncMock(return_value=[
        (
            b"processed",
            [
                (
                    b"1-0",
                    {
                        b"event": json.dumps({
                            "session_id": "session-1",
                            "event_type": "tool_call",
                        }).encode()
                    },
                )
            ],
        )
    ])

    broadcasts = []
    broadcaster = None

    class Hub:
        async def broadcast(self, session_id, event):
            broadcasts.append((session_id, event))
            broadcaster.running = False

    broadcaster = ProcessedEventBroadcaster(
        Hub(),
        stream_name="processed",
        consumer_group="broadcasters",
        consumer_name="b1",
    )

    with patch("services.realtime_broadcaster.get_redis_client", return_value=redis):
        await broadcaster.initialize()
        await broadcaster.consume_processed_events(batch_size=10, block_ms=1)

    redis.xgroup_create.assert_called_once_with(
        "processed",
        "broadcasters",
        id="0",
        mkstream=True,
    )
    redis.xreadgroup.assert_called_once()
    redis.xack.assert_called_once_with("processed", "broadcasters", b"1-0")
    assert broadcasts == [("session-1", {"session_id": "session-1", "event_type": "tool_call"})]
