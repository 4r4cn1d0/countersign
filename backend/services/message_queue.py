"""Redis Streams message queue for trace event processing."""

import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from config import settings
from services.redis_service import get_redis_client


class MessageQueueProducer:
    """Producer for publishing trace events to Redis Streams."""
    
    def __init__(self):
        self.stream_name = settings.REDIS_STREAM_NAME
        self.redis: Optional[Redis] = None
    
    async def initialize(self):
        """Initialize Redis client."""
        self.redis = await get_redis_client()
    
    async def publish_event(self, event_data: Dict[str, Any]) -> str:
        """
        Publish a single trace event to the stream.
        
        Args:
            event_data: Event data dictionary
            
        Returns:
            Message ID from Redis
        """
        if not self.redis:
            await self.initialize()
        
        # Serialize event data
        message = {
            "event": json.dumps(event_data),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add to stream
        message_id = await self.redis.xadd(self.stream_name, message)
        return message_id.decode() if isinstance(message_id, bytes) else message_id
    
    async def publish_batch(self, events: List[Dict[str, Any]]) -> List[str]:
        """
        Publish multiple events in a batch.
        
        Args:
            events: List of event data dictionaries
            
        Returns:
            List of message IDs
        """
        if not self.redis:
            await self.initialize()
        
        message_ids = []
        
        # Use pipeline for batch operations
        async with self.redis.pipeline() as pipe:
            for event_data in events:
                message = {
                    "event": json.dumps(event_data),
                    "timestamp": datetime.utcnow().isoformat()
                }
                pipe.xadd(self.stream_name, message)
            
            results = await pipe.execute()
            message_ids = [
                r.decode() if isinstance(r, bytes) else r
                for r in results
            ]
        
        return message_ids


class MessageQueueConsumer:
    """Consumer for processing trace events from Redis Streams."""
    
    def __init__(self, consumer_name: Optional[str] = None):
        self.stream_name = settings.REDIS_STREAM_NAME
        self.consumer_group = settings.REDIS_CONSUMER_GROUP
        self.consumer_name = consumer_name or settings.REDIS_CONSUMER_NAME
        self.redis: Optional[Redis] = None
        self.running = False
    
    async def initialize(self):
        """Initialize Redis client and create consumer group."""
        self.redis = await get_redis_client()
        
        # Create consumer group if it doesn't exist
        try:
            await self.redis.xgroup_create(
                self.stream_name,
                self.consumer_group,
                id="0",
                mkstream=True
            )
            print(f"✅ Created consumer group: {self.consumer_group}")
        except ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
            # Group already exists
            print(f"✅ Consumer group already exists: {self.consumer_group}")
    
    async def consume_messages(
        self,
        callback,
        batch_size: int = 10,
        block_ms: int = 1000
    ):
        """
        Consume messages from the stream and process them.
        
        Args:
            callback: Async function to process each message
            batch_size: Number of messages to read at once
            block_ms: Milliseconds to block waiting for messages
        """
        if not self.redis:
            await self.initialize()
        
        self.running = True
        print(f"🔄 Consumer {self.consumer_name} started")
        
        while self.running:
            try:
                # Read messages from consumer group
                messages = await self.redis.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    {self.stream_name: ">"},
                    count=batch_size,
                    block=block_ms
                )
                
                if not messages:
                    continue
                
                # Process each message
                for stream_name, stream_messages in messages:
                    for message_id, message_data in stream_messages:
                        try:
                            # Decode message
                            event_json = message_data.get(b"event") or message_data.get("event")
                            if isinstance(event_json, bytes):
                                event_json = event_json.decode()
                            
                            event_data = json.loads(event_json)
                            
                            # Process message
                            await callback(event_data)
                            
                            # Acknowledge message
                            await self.redis.xack(
                                self.stream_name,
                                self.consumer_group,
                                message_id
                            )
                        
                        except Exception as e:
                            print(f"❌ Error processing message {message_id}: {e}")
                            # Move to dead letter queue
                            await self._move_to_dlq(message_id, message_data, str(e))
            
            except Exception as e:
                print(f"❌ Consumer error: {e}")
                await asyncio.sleep(5)  # Back off on error
    
    async def _move_to_dlq(
        self,
        message_id: str,
        message_data: Dict,
        error: str
    ):
        """Move failed message to dead letter queue."""
        dlq_stream = f"{self.stream_name}:dlq"
        
        dlq_message = {
            "original_message_id": message_id,
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
            **message_data
        }
        
        await self.redis.xadd(dlq_stream, dlq_message)
        
        # Acknowledge original message to remove from pending
        await self.redis.xack(
            self.stream_name,
            self.consumer_group,
            message_id
        )
    
    async def stop(self):
        """Stop consuming messages."""
        self.running = False
        print(f"🛑 Consumer {self.consumer_name} stopped")


class MessageQueueRetryHandler:
    """Handler for retrying failed messages."""
    
    def __init__(self):
        self.redis: Optional[Redis] = None
        self.max_retries = 3
        self.retry_delay_seconds = 60
    
    async def initialize(self):
        """Initialize Redis client."""
        self.redis = await get_redis_client()
    
    async def retry_pending_messages(self, stream_name: str, consumer_group: str):
        """
        Retry messages that have been pending for too long.
        
        Args:
            stream_name: Redis stream name
            consumer_group: Consumer group name
        """
        if not self.redis:
            await self.initialize()
        
        # Get pending messages
        pending = await self.redis.xpending(stream_name, consumer_group)
        
        if pending and pending[0] > 0:
            print(f"⚠️  Found {pending[0]} pending messages")
            
            # Get detailed pending info
            pending_messages = await self.redis.xpending_range(
                stream_name,
                consumer_group,
                min="-",
                max="+",
                count=100
            )
            
            for msg_info in pending_messages:
                message_id = msg_info["message_id"]
                times_delivered = msg_info["times_delivered"]
                
                # If delivered too many times, move to DLQ
                if times_delivered >= self.max_retries:
                    print(f"⚠️  Moving message {message_id} to DLQ (retries exceeded)")
                    message_data = await self._fetch_message(stream_name, message_id)
                    await self._move_pending_to_dlq(
                        stream_name,
                        consumer_group,
                        message_id,
                        message_data,
                        f"max retries exceeded ({times_delivered})",
                    )

    async def _fetch_message(self, stream_name: str, message_id) -> Dict:
        """Fetch a pending message body by ID for DLQ preservation."""
        rows = await self.redis.xrange(stream_name, min=message_id, max=message_id, count=1)
        if not rows:
            return {}
        return rows[0][1]

    async def _move_pending_to_dlq(
        self,
        stream_name: str,
        consumer_group: str,
        message_id,
        message_data: Dict,
        error: str,
    ) -> None:
        dlq_stream = f"{stream_name}:dlq"
        dlq_message = {
            "original_message_id": message_id,
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
            **message_data,
        }
        await self.redis.xadd(dlq_stream, dlq_message)
        await self.redis.xack(stream_name, consumer_group, message_id)
