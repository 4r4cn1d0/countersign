"""In-process pub/sub for real-time WebSocket delivery."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class _ClientState:
    queue: asyncio.Queue[Optional[str]]
    sender_task: asyncio.Task
    dropped_messages: int = 0
    sessions: Set[str] = field(default_factory=set)


class EventHub:
    """Maps session IDs to connected WebSocket clients."""

    def __init__(
        self,
        client_buffer_size: Optional[int] = None,
        batch_max_size: Optional[int] = None,
        batch_window_ms: Optional[int] = None,
    ) -> None:
        self._lock = asyncio.Lock()
        self._subscribers: Dict[str, Set[WebSocket]] = {}
        self._clients: Dict[WebSocket, _ClientState] = {}
        self._client_buffer_size = client_buffer_size or settings.WS_CLIENT_BUFFER_SIZE
        self._batch_max_size = batch_max_size or settings.WS_BATCH_MAX_SIZE
        self._batch_window_seconds = (batch_window_ms if batch_window_ms is not None else settings.WS_BATCH_WINDOW_MS) / 1000

    async def subscribe(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            state = self._clients.get(websocket)
            if state is None:
                queue: asyncio.Queue[Optional[str]] = asyncio.Queue(maxsize=self._client_buffer_size)
                task = asyncio.create_task(
                    self._send_loop(websocket, queue),
                    name=f"ws-send-{id(websocket)}",
                )
                state = _ClientState(queue=queue, sender_task=task)
                self._clients[websocket] = state
            state.sessions.add(session_id)
            self._subscribers.setdefault(session_id, set()).add(websocket)

    async def unsubscribe(self, session_id: str, websocket: WebSocket) -> None:
        should_close = False
        async with self._lock:
            clients = self._subscribers.get(session_id)
            if clients:
                clients.discard(websocket)
                if not clients:
                    del self._subscribers[session_id]

            state = self._clients.get(websocket)
            if state:
                state.sessions.discard(session_id)
                should_close = not state.sessions

        if should_close:
            await self.unsubscribe_all(websocket)

    async def unsubscribe_all(self, websocket: WebSocket) -> None:
        state: Optional[_ClientState] = None
        async with self._lock:
            empty = []
            for session_id, clients in self._subscribers.items():
                clients.discard(websocket)
                if not clients:
                    empty.append(session_id)
            for session_id in empty:
                del self._subscribers[session_id]
            state = self._clients.pop(websocket, None)

        if state:
            state.sessions.clear()
            self._enqueue_sentinel(state)
            await self._stop_sender_task(state)

    async def broadcast(self, session_id: str, event: Dict[str, Any]) -> None:
        async with self._lock:
            states = [
                self._clients[ws]
                for ws in self._subscribers.get(session_id, set())
                if ws in self._clients
            ]

        if not states:
            return

        message = json.dumps({"type": "event", "session_id": session_id, "event": event}, default=str)
        for state in states:
            self._enqueue_with_backpressure(state, message)

    async def wait_idle(self, websocket: Optional[WebSocket] = None) -> None:
        """Wait until queued messages are sent. Intended for tests and shutdown checks."""
        async with self._lock:
            states = [self._clients[websocket]] if websocket in self._clients else list(self._clients.values())

        await asyncio.gather(*(state.queue.join() for state in states), return_exceptions=True)

    def dropped_count(self, websocket: WebSocket) -> int:
        state = self._clients.get(websocket)
        return state.dropped_messages if state else 0

    async def close(self, reason: str = "server_shutdown") -> None:
        """Gracefully drain and close all connected WebSocket senders."""
        async with self._lock:
            clients = list(self._clients.keys())

        for websocket in clients:
            state = self._clients.get(websocket)
            if state:
                self._enqueue_with_backpressure(
                    state,
                    json.dumps({"type": "closing", "reason": reason}),
                )
            await self.unsubscribe_all(websocket)
            try:
                await websocket.close(code=1001, reason=reason)
            except Exception as exc:
                logger.debug("WebSocket close failed during shutdown: %s", exc)

    def _enqueue_with_backpressure(self, state: _ClientState, message: str) -> None:
        if state.queue.full():
            try:
                state.queue.get_nowait()
                state.queue.task_done()
                state.dropped_messages += 1
            except asyncio.QueueEmpty:
                pass
        state.queue.put_nowait(message)

    def _enqueue_sentinel(self, state: _ClientState) -> None:
        if state.queue.full():
            try:
                state.queue.get_nowait()
                state.queue.task_done()
            except asyncio.QueueEmpty:
                pass
        state.queue.put_nowait(None)

    async def _send_loop(self, websocket: WebSocket, queue: asyncio.Queue[Optional[str]]) -> None:
        try:
            while True:
                message = await queue.get()
                if message is None:
                    queue.task_done()
                    return

                batch = [message]
                should_close_after_batch = await self._collect_batch(queue, batch)

                try:
                    await websocket.send_text(self._format_batch(batch))
                except Exception as exc:
                    logger.debug("WebSocket send failed: %s", exc)
                    for _ in batch:
                        queue.task_done()
                    await self.unsubscribe_all(websocket)
                    return

                for _ in batch:
                    queue.task_done()

                if should_close_after_batch:
                    return
        except asyncio.CancelledError:
            raise

    async def _collect_batch(self, queue: asyncio.Queue[Optional[str]], batch: list[str]) -> bool:
        """Collect queued messages briefly so network latency can be amortized."""
        should_close = False
        while len(batch) < self._batch_max_size:
            try:
                if len(batch) == 1 and self._batch_window_seconds > 0:
                    message = await asyncio.wait_for(queue.get(), timeout=self._batch_window_seconds)
                else:
                    message = queue.get_nowait()
            except (asyncio.TimeoutError, asyncio.QueueEmpty):
                break

            if message is None:
                queue.task_done()
                should_close = True
                break
            batch.append(message)
        return should_close

    @staticmethod
    def _format_batch(batch: list[str]) -> str:
        if len(batch) == 1:
            return batch[0]
        return json.dumps({
            "type": "events",
            "events": [json.loads(message) for message in batch],
        }, default=str)

    async def _stop_sender_task(self, state: _ClientState) -> None:
        if state.sender_task is asyncio.current_task():
            return
        if state.sender_task.done():
            return
        try:
            await asyncio.wait_for(state.sender_task, timeout=1.0)
        except asyncio.TimeoutError:
            state.sender_task.cancel()
            try:
                await state.sender_task
            except asyncio.CancelledError:
                pass
