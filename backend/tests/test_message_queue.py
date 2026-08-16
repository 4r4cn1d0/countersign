"""Tests for Redis Streams message queue functionality."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from services.message_queue import (
    MessageQueueProducer,
    MessageQueueConsumer,
    MessageQueueRetryHandler
)


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock(return_value=b"1234567890-0")
    redis_mock.xreadgroup = AsyncMock(return_value=[])
    redis_mock.xack = AsyncMock(return_value=1)
    redis_mock.xgroup_create = AsyncMock()
    redis_mock.xpending = AsyncMock(return_value=[0, None, None, None])
    redis_mock.xpending_range = AsyncMock(return_value=[])
    redis_mock.pipeline = MagicMock()
    
    # Mock pipeline context manager
    pipeline_mock = AsyncMock()
    pipeline_mock.xadd = MagicMock()
    pipeline_mock.execute = AsyncMock(return_value=[b"1234567890-0", b"1234567890-1"])
    pipeline_mock.__aenter__ = AsyncMock(return_value=pipeline_mock)
    pipeline_mock.__aexit__ = AsyncMock(return_value=None)
    redis_mock.pipeline.return_value = pipeline_mock
    
    return redis_mock


@pytest.fixture
def sample_event():
    """Create a sample trace event."""
    return {
        "event_id": "evt_123",
        "session_id": "session_456",
        "event_type": "reasoning_step",
        "timestamp": datetime.utcnow().isoformat(),
        "event_data": {
            "prompt": "Test prompt",
            "response": "Test response",
            "model": "gpt-4"
        }
    }


class TestMessageQueueProducer:
    """Tests for MessageQueueProducer."""
    
    @pytest.mark.asyncio
    async def test_publish_event_success(self, mock_redis, sample_event):
        """Test publishing a single event successfully."""
        producer = MessageQueueProducer()
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            message_id = await producer.publish_event(sample_event)
        
        # Verify message was published
        assert message_id == "1234567890-0"
        mock_redis.xadd.assert_called_once()
        
        # Verify message structure
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == "trace_events"  # stream name
        message = call_args[0][1]
        assert "event" in message
        assert "timestamp" in message
        
        # Verify event data is JSON serialized
        event_data = json.loads(message["event"])
        assert event_data["event_id"] == "evt_123"
        assert event_data["session_id"] == "session_456"
    
    @pytest.mark.asyncio
    async def test_publish_batch_success(self, mock_redis, sample_event):
        """Test publishing multiple events in a batch."""
        producer = MessageQueueProducer()
        events = [sample_event, {**sample_event, "event_id": "evt_124"}]
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            message_ids = await producer.publish_batch(events)
        
        # Verify batch was published
        assert len(message_ids) == 2
        assert message_ids[0] == "1234567890-0"
        assert message_ids[1] == "1234567890-1"
        
        # Verify pipeline was used
        mock_redis.pipeline.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_publish_event_initializes_redis(self, mock_redis, sample_event):
        """Test that Redis client is initialized on first publish."""
        producer = MessageQueueProducer()
        assert producer.redis is None
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await producer.publish_event(sample_event)
        
        assert producer.redis is not None


class TestMessageQueueConsumer:
    """Tests for MessageQueueConsumer."""
    
    @pytest.mark.asyncio
    async def test_initialize_creates_consumer_group(self, mock_redis):
        """Test that consumer initialization creates consumer group."""
        consumer = MessageQueueConsumer(consumer_name="test_consumer")
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await consumer.initialize()
        
        # Verify consumer group was created
        mock_redis.xgroup_create.assert_called_once_with(
            "trace_events",
            "processors",
            id="0",
            mkstream=True
        )
    
    @pytest.mark.asyncio
    async def test_initialize_handles_existing_group(self, mock_redis):
        """Test that initialization handles existing consumer group gracefully."""
        from redis.exceptions import ResponseError
        
        mock_redis.xgroup_create.side_effect = ResponseError("BUSYGROUP Consumer Group name already exists")
        consumer = MessageQueueConsumer(consumer_name="test_consumer")
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            # Should not raise exception
            await consumer.initialize()
        
        assert consumer.redis is not None
    
    @pytest.mark.asyncio
    async def test_consume_messages_processes_events(self, mock_redis, sample_event):
        """Test that consumer processes messages from stream."""
        # Mock message from Redis
        message_id = b"1234567890-0"
        message_data = {
            b"event": json.dumps(sample_event).encode(),
            b"timestamp": datetime.utcnow().isoformat().encode()
        }
        
        mock_redis.xreadgroup.return_value = [
            (b"trace_events", [(message_id, message_data)])
        ]
        
        consumer = MessageQueueConsumer(consumer_name="test_consumer")
        processed_events = []
        
        async def callback(event_data):
            processed_events.append(event_data)
            # Stop consumer after processing one message
            consumer.running = False
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await consumer.initialize()
            await consumer.consume_messages(callback, batch_size=10, block_ms=100)
        
        # Verify message was processed
        assert len(processed_events) == 1
        assert processed_events[0]["event_id"] == "evt_123"
        
        # Verify message was acknowledged
        mock_redis.xack.assert_called_once_with(
            "trace_events",
            "processors",
            message_id
        )
    
    @pytest.mark.asyncio
    async def test_consume_messages_handles_processing_error(self, mock_redis, sample_event):
        """Test that consumer moves failed messages to DLQ."""
        # Mock message from Redis
        message_id = b"1234567890-0"
        message_data = {
            b"event": json.dumps(sample_event).encode(),
            b"timestamp": datetime.utcnow().isoformat().encode()
        }
        
        mock_redis.xreadgroup.return_value = [
            (b"trace_events", [(message_id, message_data)])
        ]
        
        consumer = MessageQueueConsumer(consumer_name="test_consumer")
        
        async def failing_callback(event_data):
            consumer.running = False
            raise ValueError("Processing failed")
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await consumer.initialize()
            await consumer.consume_messages(failing_callback, batch_size=10, block_ms=100)
        
        # Verify message was moved to DLQ
        dlq_calls = [call for call in mock_redis.xadd.call_args_list 
                     if "trace_events:dlq" in str(call)]
        assert len(dlq_calls) > 0
        
        # Verify original message was acknowledged
        mock_redis.xack.assert_called()
    
    @pytest.mark.asyncio
    async def test_stop_consumer(self, mock_redis):
        """Test that consumer can be stopped gracefully."""
        consumer = MessageQueueConsumer(consumer_name="test_consumer")
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await consumer.initialize()
            consumer.running = True
            await consumer.stop()
        
        assert consumer.running is False


class TestMessageQueueRetryHandler:
    """Tests for MessageQueueRetryHandler."""
    
    @pytest.mark.asyncio
    async def test_retry_pending_messages_no_pending(self, mock_redis):
        """Test retry handler when there are no pending messages."""
        handler = MessageQueueRetryHandler()
        
        # Mock no pending messages
        mock_redis.xpending.return_value = [0, None, None, None]
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await handler.retry_pending_messages("trace_events", "processors")
        
        # Should not call xpending_range if no pending messages
        mock_redis.xpending_range.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_retry_pending_messages_with_retries(self, mock_redis, sample_event):
        """Test retry handler moves messages to DLQ after max retries."""
        handler = MessageQueueRetryHandler()
        handler.max_retries = 3
        
        # Mock pending messages
        mock_redis.xpending.return_value = [2, b"1234567890-0", b"1234567890-1", None]
        mock_redis.xpending_range.return_value = [
            {
                "message_id": b"1234567890-0",
                "consumer": b"processor_1",
                "times_delivered": 3,
                "idle_time": 60000
            },
            {
                "message_id": b"1234567890-1",
                "consumer": b"processor_1",
                "times_delivered": 1,
                "idle_time": 5000
            }
        ]
        mock_redis.xrange = AsyncMock(return_value=[
            (b"1234567890-0", {b"event": json.dumps(sample_event).encode()})
        ])
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await handler.retry_pending_messages("trace_events", "processors")
        
        mock_redis.xadd.assert_called_with(
            "trace_events:dlq",
            {
                "original_message_id": b"1234567890-0",
                "error": "max retries exceeded (3)",
                "timestamp": mock_redis.xadd.call_args.args[1]["timestamp"],
                b"event": json.dumps(sample_event).encode(),
            }
        )
        mock_redis.xack.assert_called_once_with(
            "trace_events",
            "processors",
            b"1234567890-0"
        )
    
    @pytest.mark.asyncio
    async def test_initialize_sets_redis_client(self, mock_redis):
        """Test that initialize sets Redis client."""
        handler = MessageQueueRetryHandler()
        assert handler.redis is None
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            await handler.initialize()
        
        assert handler.redis is not None


class TestMessageQueueIntegration:
    """Integration tests for message queue components."""
    
    @pytest.mark.asyncio
    async def test_producer_consumer_flow(self, mock_redis, sample_event):
        """Test end-to-end flow from producer to consumer."""
        producer = MessageQueueProducer()
        consumer = MessageQueueConsumer(consumer_name="test_consumer")
        
        # Setup mock to return published message when consuming
        published_message = None
        
        async def mock_publish(stream_name, message):
            nonlocal published_message
            published_message = message
            return b"1234567890-0"
        
        mock_redis.xadd.side_effect = mock_publish
        
        # Mock consumer to return the published message
        def mock_consume(*args, **kwargs):
            if published_message:
                message_id = b"1234567890-0"
                return [(b"trace_events", [(message_id, published_message)])]
            return []
        
        mock_redis.xreadgroup.side_effect = mock_consume
        
        processed_events = []
        
        async def callback(event_data):
            processed_events.append(event_data)
            consumer.running = False
        
        with patch('services.message_queue.get_redis_client', return_value=mock_redis):
            # Publish event
            message_id = await producer.publish_event(sample_event)
            assert message_id == "1234567890-0"
            
            # Consume event
            await consumer.initialize()
            await consumer.consume_messages(callback, batch_size=1, block_ms=100)
        
        # Verify event was processed
        assert len(processed_events) == 1
        assert processed_events[0]["event_id"] == "evt_123"
