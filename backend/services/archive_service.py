"""Session archival to S3-compatible storage (task 4.4)."""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from config import settings
from services.database import get_db_pool

logger = logging.getLogger(__name__)

_archive_task: Optional[asyncio.Task] = None


async def start_archive_worker(interval_seconds: Optional[int] = None) -> Optional[asyncio.Task]:
    """Start a background archival loop when archival is enabled."""
    global _archive_task
    if not settings.ARCHIVE_ENABLED:
        return None
    if _archive_task and not _archive_task.done():
        return _archive_task

    interval = interval_seconds or settings.ARCHIVE_INTERVAL_SECONDS
    _archive_task = asyncio.create_task(_archive_loop(interval), name="session-archive-worker")
    return _archive_task


async def stop_archive_worker() -> None:
    """Stop the background archival loop."""
    global _archive_task
    if not _archive_task:
        return
    _archive_task.cancel()
    try:
        await _archive_task
    except asyncio.CancelledError:
        pass
    _archive_task = None


async def _archive_loop(interval_seconds: int) -> None:
    while True:
        try:
            await archive_sessions_older_than()
        except Exception as exc:
            logger.warning("Archive worker iteration failed: %s", exc)
        await asyncio.sleep(interval_seconds)


async def archive_sessions_older_than(days: Optional[int] = None) -> int:
    """
    Archive sessions older than retention threshold to S3/MinIO.

    Returns the number of sessions archived. Skips if ARCHIVE_ENABLED is false
    or S3 is not configured.
    """
    if not settings.ARCHIVE_ENABLED:
        logger.info("Archival disabled (ARCHIVE_ENABLED=false)")
        return 0

    retention_days = days or settings.WARM_STORAGE_DAYS
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT session_id FROM sessions
            WHERE created_at < $1 AND status IN ('completed', 'failed', 'timeout', 'cancelled')
            LIMIT 100
            """,
            cutoff,
        )

    if not rows:
        return 0

    archived = 0
    for row in rows:
        session_id = row["session_id"]
        payload = await _export_session(session_id)
        if settings.S3_ENDPOINT or settings.S3_ACCESS_KEY:
            try:
                _upload_to_s3(session_id, payload)
                await _delete_hot_session(session_id)
                archived += 1
            except Exception as exc:
                logger.error("Failed to archive session %s: %s", session_id, exc)
        else:
            logger.warning(
                "S3 not configured; would archive session %s (%d bytes)",
                session_id,
                len(json.dumps(payload)),
            )

    return archived


async def _export_session(session_id) -> Dict[str, Any]:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        session = await conn.fetchrow("SELECT * FROM sessions WHERE session_id = $1", session_id)
        events = await conn.fetch(
            "SELECT * FROM trace_events WHERE session_id = $1 ORDER BY sequence_number",
            session_id,
        )
    return {
        "session": dict(session) if session else {},
        "events": [dict(e) for e in events],
        "archived_at": datetime.utcnow().isoformat(),
    }


def _upload_to_s3(session_id, payload: Dict[str, Any]) -> None:
    import boto3

    client_kwargs: Dict[str, Any] = {}
    if settings.S3_ENDPOINT:
        client_kwargs["endpoint_url"] = settings.S3_ENDPOINT
    if settings.S3_ACCESS_KEY:
        client_kwargs["aws_access_key_id"] = settings.S3_ACCESS_KEY
        client_kwargs["aws_secret_access_key"] = settings.S3_SECRET_KEY

    client = boto3.client("s3", **client_kwargs)
    body = gzip.compress(json.dumps(payload, default=str).encode("utf-8"))
    key = f"sessions/{session_id}.json.gz"
    client.put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=body,
        ContentEncoding="gzip",
        ContentType="application/json",
    )


async def _delete_hot_session(session_id) -> None:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM sessions WHERE session_id = $1", session_id)
