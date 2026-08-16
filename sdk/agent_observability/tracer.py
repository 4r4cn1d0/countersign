"""AgentTracer — HTTP client with buffering and retry."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import httpx


class AgentTracer:
    """Buffers trace events and flushes them to the observability API."""

    def __init__(
        self,
        api_key: str,
        endpoint: str = "http://localhost:8000",
        buffer_size: int = 100,
        flush_interval_seconds: float = 5.0,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.buffer_size = buffer_size
        self.flush_interval_seconds = flush_interval_seconds
        self.max_retries = max_retries
        self._buffer: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._session_id: Optional[UUID] = None
        self._sequence = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._client = httpx.Client(timeout=30.0)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def start_session(
        self,
        agent_type: str,
        goal: str,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> UUID:
        response = self._client.post(
            f"{self.endpoint}/api/v1/sessions",
            headers=self._headers(),
            json={
                "agent_type": agent_type,
                "goal": goal,
                "metadata": metadata or {},
                "tags": tags or [],
            },
        )
        response.raise_for_status()
        self._session_id = UUID(response.json()["session_id"])
        self._sequence = 0
        self._start_flush_thread()
        return self._session_id

    def _start_flush_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    def _flush_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(self.flush_interval_seconds)
            try:
                self.flush()
            except Exception:
                pass

    def record_event(self, event: Dict[str, Any]) -> None:
        if self._session_id is None:
            raise RuntimeError("Call start_session() before recording events")

        self._sequence += 1
        payload = {
            "event_id": str(uuid4()),
            "session_id": str(self._session_id),
            "sequence_number": self._sequence,
            "timestamp": datetime.utcnow().isoformat(),
            **event,
        }
        flush_now = False
        with self._lock:
            self._buffer.append(payload)
            if len(self._buffer) >= self.buffer_size:
                flush_now = True
        if flush_now:
            self.flush()

    @contextmanager
    def tool_call(
        self,
        tool_name: str,
        tool_type: str = "function",
        inputs: Optional[Dict[str, Any]] = None,
        **metadata: Any,
    ):
        """Record a tool call around manually instrumented code."""
        start = datetime.utcnow()
        try:
            yield
        except Exception as exc:
            self.record_event({
                "event_type": "tool_call",
                "tool_name": tool_name,
                "tool_type": tool_type,
                "inputs": inputs or {},
                "start_time": start.isoformat(),
                "end_time": datetime.utcnow().isoformat(),
                "duration_ms": int((datetime.utcnow() - start).total_seconds() * 1000),
                "status": "failed",
                "error": {"type": type(exc).__name__, "message": str(exc)},
                **metadata,
            })
            raise
        else:
            self.record_event({
                "event_type": "tool_call",
                "tool_name": tool_name,
                "tool_type": tool_type,
                "inputs": inputs or {},
                "start_time": start.isoformat(),
                "end_time": datetime.utcnow().isoformat(),
                "duration_ms": int((datetime.utcnow() - start).total_seconds() * 1000),
                "status": "completed",
                **metadata,
            })

    @asynccontextmanager
    async def atool_call(
        self,
        tool_name: str,
        tool_type: str = "function",
        inputs: Optional[Dict[str, Any]] = None,
        **metadata: Any,
    ):
        """Async variant of tool_call for manual instrumentation."""
        with self.tool_call(tool_name, tool_type=tool_type, inputs=inputs, **metadata):
            yield

    def record_custom_metric(
        self,
        name: str,
        value: Any,
        metric_type: str = "gauge",
        unit: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        self.record_event({
            "event_type": "custom_metric",
            "metric_name": name,
            "metric_value": value,
            "metric_type": metric_type,
            "unit": unit,
            "tags": tags or {},
        })

    def annotate(
        self,
        text: str,
        annotation_type: str = "note",
        related_event_ids: Optional[List[str]] = None,
    ) -> None:
        self.record_event({
            "event_type": "annotation",
            "text": text,
            "annotation_type": annotation_type,
            "related_event_ids": related_event_ids or [],
        })

    def flush(self) -> None:
        with self._lock:
            if not self._buffer or self._session_id is None:
                return
            batch = list(self._buffer)
            self._buffer.clear()

        self._post_with_retry(
            f"{self.endpoint}/api/v1/sessions/{self._session_id}/events",
            {"events": batch},
        )

    def _post_with_retry(self, url: str, body: Dict[str, Any]) -> None:
        delay = 1.0
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = self._client.post(url, headers=self._headers(), json=body)
                response.raise_for_status()
                return
            except Exception as exc:
                last_error = exc
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
        if last_error:
            raise last_error

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self.flush()
        self._client.close()

    async def aflush(self) -> None:
        await asyncio.to_thread(self.flush)
