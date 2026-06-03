"""Trace event enrichment and persistence service."""

from __future__ import annotations

import hashlib
import asyncio
import json
import logging
import math
from collections import deque
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, Optional
from uuid import UUID

from services.database import get_db_pool

logger = logging.getLogger(__name__)

COMMON_EVENT_FIELDS = frozenset({
    "event_id",
    "session_id",
    "event_type",
    "timestamp",
    "sequence_number",
    "parent_event_id",
    "duration_ms",
    "status",
    "error",
})

EVENT_TYPE_COUNTERS = {
    "reasoning_step": "total_reasoning_steps",
    "tool_call": "total_tool_calls",
    "memory_access": "total_memory_accesses",
}

RECENT_EVENT_HASHES: Dict[str, deque] = {}
RECENT_CACHE_SIZE = 50
LOOP_REPEAT_THRESHOLD = 5

# Optional hook invoked after a trace event is persisted (e.g. WebSocket fan-out).
_event_processed_hooks: list[Callable[[Dict[str, Any]], Any]] = []


def register_event_processed_hook(callback: Callable[[Dict[str, Any]], Any]) -> None:
    if callback not in _event_processed_hooks:
        _event_processed_hooks.append(callback)


def clear_event_processed_hooks() -> None:
    _event_processed_hooks.clear()


def _normalize_timestamp(timestamp: Any) -> datetime:
    if isinstance(timestamp, datetime):
        return timestamp
    if isinstance(timestamp, str):
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
            raise ValueError("Invalid timestamp format for trace event") from exc
    if isinstance(timestamp, (int, float)):
        return datetime.utcfromtimestamp(float(timestamp))
    raise ValueError("Invalid timestamp format for trace event")


def _extract_error_fields(event_data: Dict[str, Any]) -> Dict[str, Optional[str]]:
    error_value = event_data.get("error")
    if not error_value:
        return {"error_type": None, "error_message": None}

    if isinstance(error_value, dict):
        return {
            "error_type": error_value.get("type") or error_value.get("error_type"),
            "error_message": error_value.get("message") or error_value.get("error"),
        }

    return {"error_type": type(error_value).__name__, "error_message": str(error_value)}


def _extract_event_payload(event_data: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in event_data.items() if k not in COMMON_EVENT_FIELDS}


def _compute_aggregate_deltas(event_data: Dict[str, Any]) -> Dict[str, Any]:
    event_type = event_data.get("event_type")
    deltas = {
        "total_reasoning_steps": 0,
        "total_tool_calls": 0,
        "total_memory_accesses": 0,
        "total_memory_hits": 0,
        "total_tokens": 0,
        "total_cost": Decimal("0"),
        "error_count": 0,
    }

    counter_key = EVENT_TYPE_COUNTERS.get(event_type)
    if counter_key:
        deltas[counter_key] = 1

    if event_type == "reasoning_step":
        input_tokens = int(event_data.get("input_tokens") or 0)
        output_tokens = int(event_data.get("output_tokens") or 0)
        deltas["total_tokens"] = input_tokens + output_tokens
        try:
            deltas["total_cost"] = Decimal(str(event_data.get("cost") or 0))
        except Exception:
            deltas["total_cost"] = Decimal("0")

    if event_data.get("status") == "failed" or event_data.get("error") is not None:
        deltas["error_count"] = 1

    if event_type == "memory_access":
        results = event_data.get("results") or []
        num_results = int(event_data.get("num_results") or len(results) or 0)
        if num_results > 0:
            deltas["total_memory_hits"] = 1

    return deltas


def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    freq: Dict[str, int] = {}
    for ch in text:
        freq[ch] = freq.get(ch, 0) + 1
    entropy = 0.0
    length = len(text)
    for count in freq.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def _estimate_confidence(event_payload: Dict[str, Any]) -> float:
    conf = event_payload.get("confidence")
    if isinstance(conf, (int, float)):
        return max(0.0, min(1.0, float(conf)))

    text = "".join(str(event_payload.get(k, "")) for k in ("output", "response", "content", "prompt"))
    length = len(text)
    if length == 0:
        return 0.0
    score = 1.0 - 1.0 / (1.0 + math.log1p(length))
    return max(0.0, min(1.0, score))


def _hash_payload(payload: Dict[str, Any]) -> str:
    try:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    except TypeError:
        serialized = str(payload)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _is_infinite_loop(session_id: str, payload_hash: str) -> bool:
    dq = RECENT_EVENT_HASHES.setdefault(session_id, deque(maxlen=RECENT_CACHE_SIZE))
    count = sum(1 for h in dq if h == payload_hash)
    dq.append(payload_hash)
    return count + 1 >= LOOP_REPEAT_THRESHOLD


async def _upsert_tool_call_metric(
    conn,
    event_data: Dict[str, Any],
    timestamp: datetime,
) -> None:
    tool_name = event_data.get("tool_name") or "unknown"
    success = 1 if event_data.get("status") != "failed" and not event_data.get("error") else 0
    failure = 1 - success
    duration = int(event_data.get("duration_ms") or 0)

    await conn.execute(
        """
        INSERT INTO tool_call_metrics (
            timestamp, tool_name, success_count, failure_count,
            total_duration_ms, avg_duration_ms
        ) VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (timestamp, tool_name) DO UPDATE SET
            success_count = tool_call_metrics.success_count + EXCLUDED.success_count,
            failure_count = tool_call_metrics.failure_count + EXCLUDED.failure_count,
            total_duration_ms = tool_call_metrics.total_duration_ms + EXCLUDED.total_duration_ms,
            avg_duration_ms = (
                tool_call_metrics.total_duration_ms + EXCLUDED.total_duration_ms
            ) / GREATEST(
                tool_call_metrics.success_count + tool_call_metrics.failure_count
                + EXCLUDED.success_count + EXCLUDED.failure_count,
                1
            )
        """,
        timestamp.replace(minute=0, second=0, microsecond=0),
        tool_name,
        success,
        failure,
        duration,
        duration if duration else 0,
    )


async def process_trace_event(event_data: Dict[str, Any]) -> None:
    """Validate, enrich, and persist a trace event from the message queue."""
    await _process_trace_event_with_retry(event_data)


async def _process_trace_event_with_retry(event_data: Dict[str, Any], max_attempts: int = 3) -> None:
    delay = 0.25
    last_error: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            await _process_trace_event_once(event_data)
            return
        except Exception as exc:
            last_error = exc
            if attempt == max_attempts - 1:
                break
            await asyncio.sleep(delay)
            delay = min(delay * 2, 2.0)
    if last_error:
        raise last_error


async def _process_trace_event_once(event_data: Dict[str, Any]) -> None:
    """Validate, enrich, and persist one trace event attempt."""
    event_id = event_data.get("event_id")
    session_id = event_data.get("session_id")
    event_type = event_data.get("event_type")

    if not event_id or not session_id or not event_type:
        raise ValueError("Trace event must include event_id, session_id, and event_type")

    timestamp_raw = event_data.get("timestamp") or datetime.utcnow().isoformat()
    timestamp = _normalize_timestamp(timestamp_raw)
    sequence_number = int(event_data.get("sequence_number") or 0)
    parent_event_id = event_data.get("parent_event_id")
    duration_ms = event_data.get("duration_ms")
    status = event_data.get("status")

    error_fields = _extract_error_fields(event_data)
    event_payload = _extract_event_payload(event_data)

    combined_text = "".join(
        str(event_payload.get(k, "")) for k in ("content", "output", "response", "prompt")
    )
    entropy = _shannon_entropy(combined_text)
    confidence = _estimate_confidence(event_payload)
    event_payload.setdefault("_enrichment", {})
    event_payload["_enrichment"]["entropy"] = entropy
    event_payload["_enrichment"]["confidence"] = confidence

    payload_hash = _hash_payload(event_payload)
    if event_type == "reasoning_step" and _is_infinite_loop(str(session_id), payload_hash):
        event_payload["_enrichment"]["infinite_loop_detected"] = True

    aggregates = _compute_aggregate_deltas(event_data)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            inserted = await conn.fetchval(
                """
                INSERT INTO trace_events (
                    event_id, session_id, event_type, timestamp, sequence_number,
                    parent_event_id, duration_ms, status, event_data,
                    error_type, error_message
                ) VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6::uuid, $7, $8, $9::jsonb, $10, $11)
                ON CONFLICT (session_id, timestamp, event_id) DO NOTHING
                RETURNING event_id
                """,
                str(event_id),
                str(session_id),
                event_type,
                timestamp,
                sequence_number,
                str(parent_event_id) if parent_event_id else None,
                duration_ms,
                status,
                json.dumps(event_payload, default=str),
                error_fields["error_type"],
                error_fields["error_message"],
            )

            if inserted is None:
                return

            await conn.execute(
                """
                UPDATE sessions SET
                    total_reasoning_steps = total_reasoning_steps + $2,
                    total_tool_calls = total_tool_calls + $3,
                    total_memory_accesses = total_memory_accesses + $4,
                    total_memory_hits = total_memory_hits + $5,
                    total_tokens = total_tokens + $6,
                    total_cost = total_cost + $7,
                    error_count = error_count + $8
                WHERE session_id = $1::uuid
                """,
                str(session_id),
                aggregates["total_reasoning_steps"],
                aggregates["total_tool_calls"],
                aggregates["total_memory_accesses"],
                aggregates["total_memory_hits"],
                aggregates["total_tokens"],
                aggregates["total_cost"],
                aggregates["error_count"],
            )

            if event_type == "tool_call":
                await _upsert_tool_call_metric(conn, event_data, timestamp)

    enriched = {**event_data, **event_payload}
    for hook in _event_processed_hooks:
        try:
            result = hook(enriched)
            if hasattr(result, "__await__"):
                await result
        except Exception as exc:
            logger.warning("Event processed hook failed: %s", exc)
