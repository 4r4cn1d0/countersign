"""Reconnectable WebSocket client for real-time session subscriptions."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

EventHandler = Callable[[Dict[str, Any]], Awaitable[None]]
SnapshotHandler = Callable[[List[Dict[str, Any]]], Awaitable[None]]


@dataclass
class ReconnectPolicy:
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    multiplier: float = 2.0
    max_attempts: Optional[int] = None

    def delay_for_attempt(self, attempt: int) -> float:
        delay = self.initial_delay_seconds * (self.multiplier ** max(attempt - 1, 0))
        return min(delay, self.max_delay_seconds)


class ReconnectingWebSocketClient:
    """Client helper with exponential backoff and resumable subscriptions."""

    def __init__(
        self,
        url: str,
        token: str,
        session_id: str,
        reconnect_policy: Optional[ReconnectPolicy] = None,
        connect_factory: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self.url = url
        self.token = token
        self.session_id = session_id
        self.reconnect_policy = reconnect_policy or ReconnectPolicy()
        self.connect_factory = connect_factory
        self.last_sequence_number: Optional[int] = None
        self.running = False

    async def run(
        self,
        on_event: EventHandler,
        on_snapshot: Optional[SnapshotHandler] = None,
    ) -> None:
        """Connect, subscribe, and reconnect until stopped or attempts are exhausted."""
        self.running = True
        attempt = 0
        while self.running:
            try:
                await self._connect_and_receive(on_event, on_snapshot)
                attempt = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                attempt += 1
                logger.warning("WebSocket connection failed on attempt %s: %s", attempt, exc)
                if self.reconnect_policy.max_attempts and attempt >= self.reconnect_policy.max_attempts:
                    raise
                await asyncio.sleep(self.reconnect_policy.delay_for_attempt(attempt))

    def stop(self) -> None:
        self.running = False

    async def _connect_and_receive(
        self,
        on_event: EventHandler,
        on_snapshot: Optional[SnapshotHandler],
    ) -> None:
        connect = self.connect_factory or self._default_connect
        uri = self._url_with_token()
        async with connect(uri) as websocket:
            await self._subscribe(websocket)
            async for raw_message in websocket:
                await self._handle_message(websocket, raw_message, on_event, on_snapshot)

    async def _subscribe(self, websocket: Any) -> None:
        payload: Dict[str, Any] = {
            "type": "subscribe",
            "session_id": self.session_id,
        }
        if self.last_sequence_number is not None:
            payload["last_sequence_number"] = self.last_sequence_number
        await websocket.send(json.dumps(payload))

    async def _handle_message(
        self,
        websocket: Any,
        raw_message: str,
        on_event: EventHandler,
        on_snapshot: Optional[SnapshotHandler],
    ) -> None:
        message = json.loads(raw_message)
        msg_type = message.get("type")

        if msg_type == "ping":
            await websocket.send(json.dumps({"type": "pong"}))
            return

        if msg_type == "snapshot":
            events = message.get("events", [])
            for event in events:
                self._track_sequence(event)
            if on_snapshot:
                await on_snapshot(events)
            return

        if msg_type == "event":
            event = message.get("event", {})
            self._track_sequence(event)
            await on_event(event)
            return

        if msg_type == "events":
            for envelope in message.get("events", []):
                event = envelope.get("event", envelope)
                self._track_sequence(event)
                await on_event(event)
            return

        if msg_type == "closing":
            raise ConnectionError(message.get("reason", "server closing connection"))

        if msg_type == "error":
            raise ConnectionError(message.get("message", "websocket error"))

    def _track_sequence(self, event: Dict[str, Any]) -> None:
        sequence_number = event.get("sequence_number")
        if sequence_number is None:
            return
        try:
            sequence_number = int(sequence_number)
        except (TypeError, ValueError):
            return
        if self.last_sequence_number is None or sequence_number > self.last_sequence_number:
            self.last_sequence_number = sequence_number

    def _url_with_token(self) -> str:
        separator = "&" if "?" in self.url else "?"
        return f"{self.url}{separator}token={self.token}"

    @staticmethod
    def _default_connect(uri: str):
        import websockets

        return websockets.connect(uri)
