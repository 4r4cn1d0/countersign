"""Background worker that drains Redis Streams into PostgreSQL."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Tuple

from services.message_queue import MessageQueueConsumer
from services.trace_processor import process_trace_event

logger = logging.getLogger(__name__)

_consumer: Optional[MessageQueueConsumer] = None
_task: Optional[asyncio.Task] = None


async def start_pipeline_worker() -> Tuple[MessageQueueConsumer, asyncio.Task]:
    """Start the trace processing consumer as a background task."""
    global _consumer, _task

    if _task and not _task.done():
        return _consumer, _task

    consumer = MessageQueueConsumer()
    await consumer.initialize()
    _consumer = consumer
    _task = asyncio.create_task(
        consumer.consume_messages(process_trace_event, batch_size=10, block_ms=1000),
        name="trace-pipeline-worker",
    )
    logger.info("Trace pipeline worker started")
    return consumer, _task


async def stop_pipeline_worker() -> None:
    """Stop the background consumer."""
    global _consumer, _task

    if _consumer:
        await _consumer.stop()
        _consumer = None

    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None

    logger.info("Trace pipeline worker stopped")
