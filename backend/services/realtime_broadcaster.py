"""Redis-backed real-time broadcaster for processed trace events."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from config import settings
from services.event_hub import EventHub
from services.redis_service import get_redis_client

logger = logging.getLogger(__name__)

_publisher: Optional["ProcessedEventPublisher"] = None
_broadcaster: Optional["ProcessedEventBroadcaster"] = None
_broadcaster_task: Optional[asyncio.Task] = None


class ProcessedEventPublisher:
    """Publishes processed trace events to a Redis stream for WebSocket fan-out."""

    def __init__(self, stream_name: Optional[str] = None) -> None:
        self.stream_name = stream_name or settings.REDIS_PROCESSED_STREAM_NAME
        self.redis: Optional[Redis] = None

    async def initialize(self) -> None:
        self.redis = await get_redis_client()

    async def publish(self, event: Dict[str, Any]) -> str:
        if not self.redis:
            await self.initialize()

        session_id = str(event.get("session_id", ""))
        message = {
            "session_id": session_id,
            "event": json.dumps(event, default=str),
            "timestamp": datetime.utcnow().isoformat(),
        }
        message_id = await self.redis.xadd(self.stream_name, message)
        return message_id.decode() if isinstance(message_id, bytes) else message_id


class ProcessedEventBroadcaster:
    """Consumes processed trace events from Redis and broadcasts them to WebSockets."""

    def __init__(
        self,
        hub: EventHub,
        stream_name: Optional[str] = None,
        consumer_group: Optional[str] = None,
        consumer_name: Optional[str] = None,
    ) -> None:
        self.hub = hub
        self.stream_name = stream_name or settings.REDIS_PROCESSED_STREAM_NAME
        self.consumer_group = consumer_group or settings.REDIS_BROADCASTER_GROUP
        self.consumer_name = consumer_name or settings.REDIS_BROADCASTER_NAME
        self.redis: Optional[Redis] = None
        self.running = False

    async def initialize(self) -> None:
        self.redis = await get_redis_client()
        try:
            await self.redis.xgroup_create(
                self.stream_name,
                self.consumer_group,
                id="0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def consume_processed_events(
        self,
        batch_size: int = 100,
        block_ms: int = 1000,
    ) -> None:
        if not self.redis:
            await self.initialize()

        self.running = True
        while self.running:
            try:
                messages = await self.redis.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    {self.stream_name: ">"},
                    count=batch_size,
                    block=block_ms,
                )
                if not messages:
                    continue

                for _, stream_messages in messages:
                    for message_id, message_data in stream_messages:
                        await self._handle_message(message_id, message_data)
            except Exception as exc:
                logger.warning("Processed event broadcaster error: %s", exc)
                await asyncio.sleep(1)

    async def stop(self) -> None:
        self.running = False

    async def _handle_message(self, message_id: Any, message_data: Dict[Any, Any]) -> None:
        event = self._decode_event(message_data)
        session_id = str(event.get("session_id", ""))
        if session_id:
            await self.hub.broadcast(session_id, event)
        await self.redis.xack(self.stream_name, self.consumer_group, message_id)

    @staticmethod
    def _field(message_data: Dict[Any, Any], name: str) -> Optional[Any]:
        return message_data.get(name) or message_data.get(name.encode())

    def _decode_event(self, message_data: Dict[Any, Any]) -> Dict[str, Any]:
        raw = self._field(message_data, "event")
        if isinstance(raw, bytes):
            raw = raw.decode()
        if not raw:
            return {}
        return json.loads(raw)


async def get_processed_event_publisher() -> ProcessedEventPublisher:
    global _publisher
    if _publisher is None:
        _publisher = ProcessedEventPublisher()
    return _publisher


async def publish_processed_event(event: Dict[str, Any]) -> str:
    publisher = await get_processed_event_publisher()
    return await publisher.publish(event)


async def start_realtime_broadcaster(hub: EventHub) -> Tuple[ProcessedEventBroadcaster, asyncio.Task]:
    global _broadcaster, _broadcaster_task
    if _broadcaster_task and not _broadcaster_task.done():
        return _broadcaster, _broadcaster_task

    _broadcaster = ProcessedEventBroadcaster(hub)
    await _broadcaster.initialize()
    _broadcaster_task = asyncio.create_task(
        _broadcaster.consume_processed_events(),
        name="processed-event-broadcaster",
    )
    return _broadcaster, _broadcaster_task


async def stop_realtime_broadcaster() -> None:
    global _broadcaster, _broadcaster_task
    if _broadcaster:
        await _broadcaster.stop()
    if _broadcaster_task:
        _broadcaster_task.cancel()
        try:
            await _broadcaster_task
        except asyncio.CancelledError:
            pass
    _broadcaster = None
    _broadcaster_task = None
