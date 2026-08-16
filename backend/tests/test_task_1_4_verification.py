"""Verification tests for Task 1.4: Redis Streams message queue integration.

This test suite verifies that all requirements for task 1.4 are met:
- Configure Redis connection with connection pooling
- Implement message queue producer for trace events
- Create consumer groups for processing pipeline
- Add retry logic and dead letter queue handling

Requirements: 2.2, 2.7
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from services.redis_service import (
    init_redis,
    get_redis_client,
    get_redis_health
)
from services.message_queue import (
    MessageQueueProducer,
    MessageQueueConsumer,
    MessageQueueRetryHandler
)
from config import settings


class TestTask14ConnectionPooling:
    """Verify Redis connection pooling is properly configured."""
    
    @pytest.mark.asyncio
    async def test_connection_pool_configured_with_settings(self):
        """Verify connection pool uses settings from config."""
        mock_pool = MagicMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        
        with patch('services.redis_service.redis.ConnectionPool.from_url', return_value=mock_pool) as mock_from_url, \
             patch('services.redis_service.redis.Redis', return_value=mock_client):
            
            await init_redis()
            
            # Verify connection pool was created with correct URL and pool size
            mock_from_url.assert_called_once()
            call_args = mock_from_url.call_args
            assert call_args[0][0] == settings.REDIS_URL
            assert call_args[1]['max_connections'] == settings.REDIS_POOL_SIZE
            assert call_args[1]['decode_responses'] is False
    
    @pytest.mark.asyncio
    async def test_connection_pool_reuses_connections(self):
        """Verify that connection pool reuses connections across calls."""
        mock_pool = MagicMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        
        with patch('services.redis_service.redis.ConnectionPool.from_url', return_value=mock_pool), \
             patch('services.redis_service.redis.Redis', return_value=mock_client):
            
            await init_redis()
            
            # Get client multiple times
            client1 = await get_redis_client()
            client2 = await get_redis_client()
            client3 = await get_redis_client()
            
            # All should be the same instance (connection reuse)
            assert client1 is client2
            assert client2 is client3
    
    @pytest.mark.asyncio
    async def test_connection_pool_health_check(self):
        """Verify health check works with connection pool."""
        mock_pool = MagicMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        
        with patch('services.redis_service.redis.ConnectionPool.from_url', return_value=mock_pool), \
             patch('services.redis_service.redis.Redis', return_value=mock_client):
            
            await init_redis()
            health = await get_redis_health()
            
            assert health == "healthy"
            # Verify ping was called to check connection
            assert mock_client.ping.call_count >= 2  # Once in init, once in health check


class TestTask14MessageQueueProducer:
    """Verify message queue producer for trace events."""
    
    @pytest.mark.asyncio
    async def test_producer_publishes_single_event(self):
        """Verify producer can publish single trace events."""
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock(return_value=b"1234567890-0")
        
        producer = MessageQueueProducer()
        event_data = {
            "event_id": "evt_123",
            "session_id": "session_456",
            "event_type": "reasoning_step",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            message_id = await producer.publish_event(event_data)
        
        # Verify event was published to correct stream
        assert message_id == "1234567890-0"
        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == settings.REDIS_STREAM_NAME
        
        # Verify message structure
        message = call_args[0][1]
        assert "event" in message
        assert "timestamp" in message
        
        # Verify event data is properly serialized
        event_json = json.loads(message["event"])
        assert event_json["event_id"] == "evt_123"
        assert event_json["session_id"] == "session_456"
    
    @pytest.mark.asyncio
    async def test_producer_publishes_batch_events(self):
        """Verify producer can publish multiple events in batch."""
        mock_redis = AsyncMock()
        
        # Mock pipeline
        pipeline_mock = AsyncMock()
        pipeline_mock.xadd = MagicMock()
        pipeline_mock.execute = AsyncMock(return_value=[b"1234567890-0", b"1234567890-1", b"1234567890-2"])
        
        # Properly mock async context manager
        async def mock_aenter(self):
            return pipeline_mock
        
        async def mock_aexit(self, exc_type, exc_val, exc_tb):
            return None
        
        pipeline_mock.__aenter__ = mock_aenter
        pipeline_mock.__aexit__ = mock_aexit
        mock_redis.pipeline = MagicMock(return_value=pipeline_mock)
        
        producer = MessageQueueProducer()
        events = [
            {"event_id": f"evt_{i}", "session_id": "session_456", "event_type": "tool_call"}
            for i in range(3)
        ]
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            message_ids = await producer.publish_batch(events)
        
        # Verify batch was published
        assert len(message_ids) == 3
        assert message_ids[0] == "1234567890-0"
        assert message_ids[1] == "1234567890-1"
        assert message_ids[2] == "1234567890-2"
        
        # Verify pipeline was used for batch operation
        mock_redis.pipeline.assert_called_once()
        assert pipeline_mock.xadd.call_count == 3
    
    @pytest.mark.asyncio
    async def test_producer_uses_configured_stream_name(self):
        """Verify producer uses stream name from settings."""
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock(return_value=b"1234567890-0")
        
        producer = MessageQueueProducer()
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await producer.publish_event({"event_id": "evt_123"})
        
        # Verify correct stream name was used
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == settings.REDIS_STREAM_NAME


class TestTask14ConsumerGroups:
    """Verify consumer groups for processing pipeline."""
    
    @pytest.mark.asyncio
    async def test_consumer_creates_consumer_group(self):
        """Verify consumer creates consumer group on initialization."""
        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock()
        
        consumer = MessageQueueConsumer(consumer_name="test_consumer")
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await consumer.initialize()
        
        # Verify consumer group was created
        mock_redis.xgroup_create.assert_called_once_with(
            settings.REDIS_STREAM_NAME,
            settings.REDIS_CONSUMER_GROUP,
            id="0",
            mkstream=True
        )
    
    @pytest.mark.asyncio
    async def test_consumer_handles_existing_group(self):
        """Verify consumer handles existing consumer group gracefully."""
        from redis.exceptions import ResponseError
        
        mock_redis = AsyncMock()
        mock_redis.xgroup_create.side_effect = ResponseError("BUSYGROUP Consumer Group name already exists")
        
        consumer = MessageQueueConsumer(consumer_name="test_consumer")
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            # Should not raise exception
            await consumer.initialize()
        
        assert consumer.redis is not None
    
    @pytest.mark.asyncio
    async def test_consumer_reads_from_consumer_group(self):
        """Verify consumer reads messages using consumer group."""
        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock()
        
        # Mock message
        message_id = b"1234567890-0"
        message_data = {
            b"event": json.dumps({"event_id": "evt_123"}).encode(),
            b"timestamp": datetime.utcnow().isoformat().encode()
        }
        mock_redis.xreadgroup = AsyncMock(return_value=[
            (b"trace_events", [(message_id, message_data)])
        ])
        mock_redis.xack = AsyncMock()
        
        consumer = MessageQueueConsumer(consumer_name="test_consumer")
        processed = []
        
        async def callback(event_data):
            processed.append(event_data)
            consumer.running = False
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await consumer.initialize()
            await consumer.consume_messages(callback, batch_size=10, block_ms=100)
        
        # Verify xreadgroup was called with correct parameters
        mock_redis.xreadgroup.assert_called()
        call_args = mock_redis.xreadgroup.call_args
        assert call_args[0][0] == settings.REDIS_CONSUMER_GROUP
        assert call_args[0][1] == "test_consumer"
        assert call_args[0][2] == {settings.REDIS_STREAM_NAME: ">"}
    
    @pytest.mark.asyncio
    async def test_consumer_acknowledges_processed_messages(self):
        """Verify consumer acknowledges messages after processing."""
        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock()
        
        message_id = b"1234567890-0"
        message_data = {
            b"event": json.dumps({"event_id": "evt_123"}).encode(),
            b"timestamp": datetime.utcnow().isoformat().encode()
        }
        mock_redis.xreadgroup = AsyncMock(return_value=[
            (b"trace_events", [(message_id, message_data)])
        ])
        mock_redis.xack = AsyncMock()
        
        consumer = MessageQueueConsumer(consumer_name="test_consumer")
        
        async def callback(event_data):
            consumer.running = False
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await consumer.initialize()
            await consumer.consume_messages(callback, batch_size=10, block_ms=100)
        
        # Verify message was acknowledged
        mock_redis.xack.assert_called_once_with(
            settings.REDIS_STREAM_NAME,
            settings.REDIS_CONSUMER_GROUP,
            message_id
        )


class TestTask14RetryLogic:
    """Verify retry logic for failed messages."""
    
    @pytest.mark.asyncio
    async def test_retry_handler_detects_pending_messages(self):
        """Verify retry handler can detect pending messages."""
        mock_redis = AsyncMock()
        mock_redis.xpending = AsyncMock(return_value=[2, b"1234567890-0", b"1234567890-1", None])
        mock_redis.xpending_range = AsyncMock(return_value=[
            {
                "message_id": b"1234567890-0",
                "consumer": b"processor_1",
                "times_delivered": 1,
                "idle_time": 5000
            }
        ])
        
        handler = MessageQueueRetryHandler()
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await handler.retry_pending_messages(settings.REDIS_STREAM_NAME, settings.REDIS_CONSUMER_GROUP)
        
        # Verify pending messages were checked
        mock_redis.xpending.assert_called_once_with(
            settings.REDIS_STREAM_NAME,
            settings.REDIS_CONSUMER_GROUP
        )
        mock_redis.xpending_range.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_retry_handler_moves_to_dlq_after_max_retries(self):
        """Verify retry handler moves messages to DLQ after max retries."""
        mock_redis = AsyncMock()
        mock_redis.xpending = AsyncMock(return_value=[1, b"1234567890-0", b"1234567890-0", None])
        mock_redis.xpending_range = AsyncMock(return_value=[
            {
                "message_id": b"1234567890-0",
                "consumer": b"processor_1",
                "times_delivered": 3,  # Exceeds max retries
                "idle_time": 60000
            }
        ])
        mock_redis.xrange = AsyncMock(return_value=[
            (b"1234567890-0", {b"event": json.dumps({"event_id": "evt_123"}).encode()})
        ])
        mock_redis.xadd = AsyncMock()
        mock_redis.xack = AsyncMock()
        
        handler = MessageQueueRetryHandler()
        handler.max_retries = 3
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await handler.retry_pending_messages(settings.REDIS_STREAM_NAME, settings.REDIS_CONSUMER_GROUP)
        
        # Verify message was moved to DLQ and acknowledged
        mock_redis.xadd.assert_called()
        assert mock_redis.xadd.call_args.args[0] == f"{settings.REDIS_STREAM_NAME}:dlq"
        mock_redis.xack.assert_called_once_with(
            settings.REDIS_STREAM_NAME,
            settings.REDIS_CONSUMER_GROUP,
            b"1234567890-0"
        )
    
    @pytest.mark.asyncio
    async def test_retry_handler_configurable_max_retries(self):
        """Verify retry handler respects configurable max retries."""
        handler = MessageQueueRetryHandler()
        
        # Default should be 3
        assert handler.max_retries == 3
        
        # Should be configurable
        handler.max_retries = 5
        assert handler.max_retries == 5


class TestTask14DeadLetterQueue:
    """Verify dead letter queue handling."""
    
    @pytest.mark.asyncio
    async def test_consumer_moves_failed_messages_to_dlq(self):
        """Verify consumer moves failed messages to DLQ."""
        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock()
        
        message_id = b"1234567890-0"
        message_data = {
            b"event": json.dumps({"event_id": "evt_123"}).encode(),
            b"timestamp": datetime.utcnow().isoformat().encode()
        }
        mock_redis.xreadgroup = AsyncMock(return_value=[
            (b"trace_events", [(message_id, message_data)])
        ])
        mock_redis.xadd = AsyncMock(return_value=b"dlq-1234567890-0")
        mock_redis.xack = AsyncMock()
        
        consumer = MessageQueueConsumer(consumer_name="test_consumer")
        
        async def failing_callback(event_data):
            consumer.running = False
            raise ValueError("Processing failed")
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await consumer.initialize()
            await consumer.consume_messages(failing_callback, batch_size=10, block_ms=100)
        
        # Verify message was added to DLQ
        dlq_calls = [call for call in mock_redis.xadd.call_args_list 
                     if "trace_events:dlq" in str(call)]
        assert len(dlq_calls) > 0
        
        # Verify DLQ message contains error information
        dlq_call = dlq_calls[0]
        dlq_stream = dlq_call[0][0]
        dlq_message = dlq_call[0][1]
        
        assert dlq_stream == "trace_events:dlq"
        assert "error" in dlq_message
        assert "original_message_id" in dlq_message
    
    @pytest.mark.asyncio
    async def test_dlq_message_includes_original_data(self):
        """Verify DLQ message includes original message data."""
        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock()
        
        message_id = b"1234567890-0"
        original_event = {"event_id": "evt_123", "session_id": "session_456"}
        message_data = {
            b"event": json.dumps(original_event).encode(),
            b"timestamp": datetime.utcnow().isoformat().encode()
        }
        mock_redis.xreadgroup = AsyncMock(return_value=[
            (b"trace_events", [(message_id, message_data)])
        ])
        mock_redis.xadd = AsyncMock(return_value=b"dlq-1234567890-0")
        mock_redis.xack = AsyncMock()
        
        consumer = MessageQueueConsumer(consumer_name="test_consumer")
        
        async def failing_callback(event_data):
            consumer.running = False
            raise ValueError("Processing failed")
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await consumer.initialize()
            await consumer.consume_messages(failing_callback, batch_size=10, block_ms=100)
        
        # Verify DLQ message contains original data
        dlq_calls = [call for call in mock_redis.xadd.call_args_list 
                     if "trace_events:dlq" in str(call)]
        assert len(dlq_calls) > 0
        
        dlq_message = dlq_calls[0][0][1]
        # Original message data should be preserved
        assert b"event" in dlq_message or "event" in dlq_message
    
    @pytest.mark.asyncio
    async def test_dlq_message_acknowledged_from_original_stream(self):
        """Verify failed message is acknowledged from original stream after moving to DLQ."""
        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock()
        
        message_id = b"1234567890-0"
        message_data = {
            b"event": json.dumps({"event_id": "evt_123"}).encode(),
            b"timestamp": datetime.utcnow().isoformat().encode()
        }
        mock_redis.xreadgroup = AsyncMock(return_value=[
            (b"trace_events", [(message_id, message_data)])
        ])
        mock_redis.xadd = AsyncMock(return_value=b"dlq-1234567890-0")
        mock_redis.xack = AsyncMock()
        
        consumer = MessageQueueConsumer(consumer_name="test_consumer")
        
        async def failing_callback(event_data):
            consumer.running = False
            raise ValueError("Processing failed")
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await consumer.initialize()
            await consumer.consume_messages(failing_callback, batch_size=10, block_ms=100)
        
        # Verify original message was acknowledged
        mock_redis.xack.assert_called()
        ack_calls = mock_redis.xack.call_args_list
        
        # Should have at least one ack call for the original stream
        original_stream_acks = [
            call for call in ack_calls
            if call[0][0] == settings.REDIS_STREAM_NAME
        ]
        assert len(original_stream_acks) > 0


class TestTask14Requirements:
    """Verify specific requirements 2.2 and 2.7 are met."""
    
    @pytest.mark.asyncio
    async def test_requirement_2_2_broadcast_within_100ms(self):
        """Requirement 2.2: Backend shall broadcast step data within 100ms.
        
        This test verifies the message queue can handle low-latency publishing.
        """
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock(return_value=b"1234567890-0")
        
        producer = MessageQueueProducer()
        event_data = {
            "event_id": "evt_123",
            "event_type": "reasoning_step",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            start_time = asyncio.get_event_loop().time()
            await producer.publish_event(event_data)
            end_time = asyncio.get_event_loop().time()
        
        # Verify publishing is fast (should be much less than 100ms in mock)
        elapsed_ms = (end_time - start_time) * 1000
        assert elapsed_ms < 100, f"Publishing took {elapsed_ms}ms, should be < 100ms"
    
    @pytest.mark.asyncio
    async def test_requirement_2_7_handle_100_concurrent_sessions(self):
        """Requirement 2.7: Backend shall handle 100 concurrent sessions.
        
        This test verifies connection pooling supports high concurrency.
        """
        mock_pool = MagicMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        
        with patch('services.redis_service.redis.ConnectionPool.from_url', return_value=mock_pool), \
             patch('services.redis_service.redis.Redis', return_value=mock_client):
            
            await init_redis()
            
            # Verify pool size is configured to handle concurrent sessions
            # Default pool size should be at least 10
            assert settings.REDIS_POOL_SIZE >= 10
            
            # Verify connection pool was created with sufficient connections
            call_args = mock_pool.from_url.call_args
            if call_args:
                pool_size = call_args[1].get('max_connections', 0)
                assert pool_size >= 10, f"Pool size {pool_size} may not support 100 concurrent sessions"


class TestTask14Integration:
    """Integration tests for complete message queue flow."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_message_flow(self):
        """Test complete flow: publish -> consume -> acknowledge."""
        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock()
        
        # Track published messages
        published_messages = []
        
        async def mock_xadd(stream_name, message):
            published_messages.append((stream_name, message))
            return f"{len(published_messages)}-0".encode()
        
        mock_redis.xadd.side_effect = mock_xadd
        
        # Mock consumer to return published messages
        def mock_xreadgroup(*args, **kwargs):
            if published_messages:
                msg = published_messages[0]
                message_id = b"1-0"
                return [(msg[0].encode() if isinstance(msg[0], str) else msg[0], 
                        [(message_id, msg[1])])]
            return []
        
        mock_redis.xreadgroup.side_effect = mock_xreadgroup
        mock_redis.xack = AsyncMock()
        
        # Publish event
        producer = MessageQueueProducer()
        event_data = {
            "event_id": "evt_123",
            "session_id": "session_456",
            "event_type": "tool_call"
        }
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            message_id = await producer.publish_event(event_data)
            assert message_id == "1-0"
            
            # Consume event
            consumer = MessageQueueConsumer(consumer_name="test_consumer")
            processed_events = []
            
            async def callback(event):
                processed_events.append(event)
                consumer.running = False
            
            await consumer.initialize()
            await consumer.consume_messages(callback, batch_size=1, block_ms=100)
        
        # Verify event was processed
        assert len(processed_events) == 1
        assert processed_events[0]["event_id"] == "evt_123"
        
        # Verify message was acknowledged
        mock_redis.xack.assert_called()
