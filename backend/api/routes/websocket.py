"""WebSocket gateway for real-time trace streaming."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from asyncpg import Pool

from services.auth import AuthService
from services.database import get_db_pool
from services.event_hub import EventHub

logger = logging.getLogger(__name__)
router = APIRouter()


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _json_object(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _get_hub(websocket: WebSocket) -> EventHub:
    return websocket.app.state.event_hub


async def _authenticate(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    data = AuthService.verify_jwt_token(token)
    return data.user_id if data else None


async def _fetch_trace_snapshot(
    pool: Pool,
    session_id: UUID,
    user_id: str,
    limit: int = 500,
    after_sequence_number: Optional[int] = None,
) -> list[Dict[str, Any]]:
    async with pool.acquire() as conn:
        owned = await conn.fetchval(
            "SELECT 1 FROM sessions WHERE session_id = $1 AND user_id = $2",
            session_id,
            user_id,
        )
        if not owned:
            return []

        if after_sequence_number is None:
            rows = await conn.fetch(
                """
                SELECT event_id, session_id, event_type, timestamp, sequence_number,
                       parent_event_id, duration_ms, status, error_type, error_message, event_data
                FROM trace_events
                WHERE session_id = $1
                ORDER BY sequence_number ASC
                LIMIT $2
                """,
                session_id,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT event_id, session_id, event_type, timestamp, sequence_number,
                       parent_event_id, duration_ms, status, error_type, error_message, event_data
                FROM trace_events
                WHERE session_id = $1 AND sequence_number > $2
                ORDER BY sequence_number ASC
                LIMIT $3
                """,
                session_id,
                after_sequence_number,
                limit,
            )

    events = []
    for row in rows:
        events.append({
            "event_id": str(row["event_id"]),
            "session_id": str(row["session_id"]),
            "event_type": row["event_type"],
            "timestamp": row["timestamp"].isoformat(),
            "sequence_number": row["sequence_number"],
            "parent_event_id": str(row["parent_event_id"]) if row["parent_event_id"] else None,
            "duration_ms": row["duration_ms"],
            "status": row["status"],
            "error_type": _row_get(row, "error_type"),
            "error_message": _row_get(row, "error_message"),
            "event_data": _json_object(row["event_data"]),
        })
    return events


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """Real-time session event stream. Authenticate with ?token=<JWT>."""
    user_id = await _authenticate(token)
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    logger.info("WebSocket client connected: user_id=%s", user_id)
    hub = _get_hub(websocket)
    pool = await get_db_pool()
    subscribed_session: Optional[str] = None
    heartbeat_interval = websocket.app.state.ws_heartbeat_interval

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(heartbeat_interval)
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = message.get("type")

            if msg_type == "pong":
                continue

            if msg_type == "subscribe":
                session_id = message.get("session_id")
                if not session_id:
                    await websocket.send_json({"type": "error", "message": "session_id required"})
                    continue

                try:
                    session_uuid = UUID(session_id)
                except ValueError:
                    await websocket.send_json({"type": "error", "message": "Invalid session_id"})
                    continue

                if subscribed_session:
                    await hub.unsubscribe(subscribed_session, websocket)
                    logger.info("WebSocket unsubscribed before resubscribe: session_id=%s", subscribed_session)

                subscribed_session = session_id
                await hub.subscribe(session_id, websocket)
                logger.info("WebSocket subscribed: user_id=%s session_id=%s", user_id, session_id)

                last_sequence_number = message.get("last_sequence_number")
                if last_sequence_number is not None:
                    try:
                        last_sequence_number = int(last_sequence_number)
                    except (TypeError, ValueError):
                        await websocket.send_json({
                            "type": "error",
                            "message": "last_sequence_number must be an integer",
                        })
                        continue

                snapshot = await _fetch_trace_snapshot(
                    pool,
                    session_uuid,
                    user_id,
                    after_sequence_number=last_sequence_number,
                )
                await websocket.send_json({
                    "type": "snapshot",
                    "session_id": session_id,
                    "events": snapshot,
                })
                continue

            if msg_type == "unsubscribe":
                if subscribed_session:
                    await hub.unsubscribe(subscribed_session, websocket)
                    logger.info("WebSocket unsubscribed: user_id=%s session_id=%s", user_id, subscribed_session)
                    subscribed_session = None
                await websocket.send_json({"type": "unsubscribed"})
                continue

            await websocket.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: user_id=%s session_id=%s", user_id, subscribed_session)
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await hub.unsubscribe_all(websocket)
