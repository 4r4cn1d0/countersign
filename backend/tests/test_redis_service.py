"""Tests for Redis service and connection pooling."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import redis.asyncio as redis

from services.redis_service import (
    init_redis,
    close_redis,
    get_redis_client,
    get_redis_health
)


@pytest.fixture
def mock_redis_pool():
    """Create a mock Redis connection pool."""
    pool_mock = MagicMock()
    pool_mock.disconnect = AsyncMock()
    return pool_mock


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    client_mock = AsyncMock()
    client_mock.ping = AsyncMock(return_value=True)
    client_mock.close = AsyncMock()
    return client_mock


class TestRedisService:
    """Tests for Redis service initialization and management."""
    
    @pytest.mark.asyncio
    async def test_init_redis_creates_connection_pool(self, mock_redis_pool, mock_redis_client):
        """Test that init_redis creates a connection pool with correct settings."""
        with patch('services.redis_service.redis.ConnectionPool.from_url', return_value=mock_redis_pool), \
             patch('services.redis_service.redis.Redis', return_value=mock_redis_client), \
             patch('services.redis_service.settings') as mock_settings:
            
            mock_settings.REDIS_URL = "redis://localhost:6379/0"
            mock_settings.REDIS_POOL_SIZE = 10
            
            await init_redis()
            
            # Verify connection pool was created with correct parameters
            redis.ConnectionPool.from_url.assert_called_once_with(
                "redis://localhost:6379/0",
                max_connections=10,
                decode_responses=False
            )
            
            # Verify Redis client was created with the pool
            redis.Redis.assert_called_once_with(connection_pool=mock_redis_pool)
            
            # Verify connection was tested
            mock_redis_client.ping.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_init_redis_handles_connection_failure(self, mock_redis_pool):
        """Test that init_redis raises exception on connection failure."""
        failing_client = AsyncMock()
        failing_client.ping.side_effect = redis.ConnectionError("Connection failed")
        
        with patch('services.redis_service.redis.ConnectionPool.from_url', return_value=mock_redis_pool), \
             patch('services.redis_service.redis.Redis', return_value=failing_client), \
             patch('services.redis_service.settings') as mock_settings:
            
            mock_settings.REDIS_URL = "redis://localhost:6379/0"
            mock_settings.REDIS_POOL_SIZE = 10
            
            with pytest.raises(redis.ConnectionError):
                await init_redis()
    
    @pytest.mark.asyncio
    async def test_close_redis_closes_connections(self, mock_redis_pool, mock_redis_client):
        """Test that close_redis properly closes client and pool."""
        # First initialize
        with patch('services.redis_service.redis.ConnectionPool.from_url', return_value=mock_redis_pool), \
             patch('services.redis_service.redis.Redis', return_value=mock_redis_client), \
             patch('services.redis_service.settings') as mock_settings:
            
            mock_settings.REDIS_URL = "redis://localhost:6379/0"
            mock_settings.REDIS_POOL_SIZE = 10
            
            await init_redis()
        
        # Now close
        await close_redis()
        
        # Verify client and pool were closed
        mock_redis_client.close.assert_called_once()
        mock_redis_pool.disconnect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_redis_client_returns_client(self, mock_redis_pool, mock_redis_client):
        """Test that get_redis_client returns the initialized client."""
        with patch('services.redis_service.redis.ConnectionPool.from_url', return_value=mock_redis_pool), \
             patch('services.redis_service.redis.Redis', return_value=mock_redis_client), \
             patch('services.redis_service.settings') as mock_settings:
            
            mock_settings.REDIS_URL = "redis://localhost:6379/0"
            mock_settings.REDIS_POOL_SIZE = 10
            
            await init_redis()
            client = await get_redis_client()
            
            assert client is mock_redis_client
    
    @pytest.mark.asyncio
    async def test_get_redis_client_raises_if_not_initialized(self):
        """Test that get_redis_client raises error if Redis not initialized."""
        # Reset global state
        import services.redis_service as redis_service
        redis_service._redis_client = None
        
        with pytest.raises(RuntimeError, match="Redis client not initialized"):
            await get_redis_client()
    
    @pytest.mark.asyncio
    async def test_get_redis_health_returns_healthy(self, mock_redis_pool, mock_redis_client):
        """Test that health check returns healthy when Redis is working."""
        with patch('services.redis_service.redis.ConnectionPool.from_url', return_value=mock_redis_pool), \
             patch('services.redis_service.redis.Redis', return_value=mock_redis_client), \
             patch('services.redis_service.settings') as mock_settings:
            
            mock_settings.REDIS_URL = "redis://localhost:6379/0"
            mock_settings.REDIS_POOL_SIZE = 10
            
            await init_redis()
            health = await get_redis_health()
            
            assert health == "healthy"
            mock_redis_client.ping.assert_called()
    
    @pytest.mark.asyncio
    async def test_get_redis_health_returns_unhealthy_on_error(self, mock_redis_pool, mock_redis_client):
        """Test that health check returns unhealthy when Redis fails."""
        with patch('services.redis_service.redis.ConnectionPool.from_url', return_value=mock_redis_pool), \
             patch('services.redis_service.redis.Redis', return_value=mock_redis_client), \
             patch('services.redis_service.settings') as mock_settings:
            
            mock_settings.REDIS_URL = "redis://localhost:6379/0"
            mock_settings.REDIS_POOL_SIZE = 10
            
            # First initialize successfully
            mock_redis_client.ping.return_value = True
            await init_redis()
            
            # Now make ping fail for health check
            mock_redis_client.ping.side_effect = redis.ConnectionError("Connection lost")
            health = await get_redis_health()
            
            assert health == "unhealthy"


class TestRedisConnectionPooling:
    """Tests for Redis connection pooling behavior."""
    
    @pytest.mark.asyncio
    async def test_connection_pool_size_configuration(self, mock_redis_pool, mock_redis_client):
        """Test that connection pool size is configurable."""
        with patch('services.redis_service.redis.ConnectionPool.from_url', return_value=mock_redis_pool), \
             patch('services.redis_service.redis.Redis', return_value=mock_redis_client), \
             patch('services.redis_service.settings') as mock_settings:
            
            # Test with custom pool size
            mock_settings.REDIS_URL = "redis://localhost:6379/0"
            mock_settings.REDIS_POOL_SIZE = 20
            
            await init_redis()
            
            # Verify pool was created with custom size
            redis.ConnectionPool.from_url.assert_called_once()
            call_kwargs = redis.ConnectionPool.from_url.call_args[1]
            assert call_kwargs['max_connections'] == 20
    
    @pytest.mark.asyncio
    async def test_connection_pool_reuses_connections(self, mock_redis_pool, mock_redis_client):
        """Test that multiple get_redis_client calls return the same client."""
        with patch('services.redis_service.redis.ConnectionPool.from_url', return_value=mock_redis_pool), \
             patch('services.redis_service.redis.Redis', return_value=mock_redis_client), \
             patch('services.redis_service.settings') as mock_settings:
            
            mock_settings.REDIS_URL = "redis://localhost:6379/0"
            mock_settings.REDIS_POOL_SIZE = 10
            
            await init_redis()
            
            # Get client multiple times
            client1 = await get_redis_client()
            client2 = await get_redis_client()
            client3 = await get_redis_client()
            
            # All should be the same instance
            assert client1 is client2
            assert client2 is client3
            
            # Redis constructor should only be called once
            assert redis.Redis.call_count == 1
