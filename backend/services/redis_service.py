"""Redis connection and message queue service."""

import redis.asyncio as redis
from typing import Optional

from config import settings


# Global Redis connection pool
_redis_pool: Optional[redis.ConnectionPool] = None
_redis_client: Optional[redis.Redis] = None


async def init_redis():
    """Initialize Redis connection pool."""
    global _redis_pool, _redis_client
    
    try:
        _redis_pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=settings.REDIS_POOL_SIZE,
            decode_responses=False  # We'll handle encoding/decoding
        )
        _redis_client = redis.Redis(connection_pool=_redis_pool)
        
        # Test connection
        await _redis_client.ping()
        print(f"✅ Redis connected (pool size: {settings.REDIS_POOL_SIZE})")
    except Exception as e:
        print(f"❌ Failed to connect to Redis: {e}")
        raise


async def close_redis():
    """Close Redis connection pool."""
    global _redis_pool, _redis_client
    
    if _redis_client:
        await _redis_client.close()
    if _redis_pool:
        await _redis_pool.disconnect()
    print("✅ Redis connection closed")


async def get_redis_client() -> redis.Redis:
    """Get Redis client."""
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized")
    return _redis_client


async def get_redis_health() -> str:
    """Check Redis health."""
    try:
        client = await get_redis_client()
        await client.ping()
        return "healthy"
    except Exception as e:
        print(f"Redis health check failed: {e}")
        return "unhealthy"
