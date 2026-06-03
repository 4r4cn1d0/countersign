"""Database connection and management service."""

import asyncpg
from typing import Optional

from config import settings


# Global connection pool
_pool: Optional[asyncpg.Pool] = None


async def init_db():
    """Initialize database connection pool."""
    global _pool
    
    try:
        _pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=5,
            max_size=settings.DB_POOL_SIZE,
            max_inactive_connection_lifetime=300,
            command_timeout=60
        )
        print(f"✅ Database pool created (size: {settings.DB_POOL_SIZE})")
    except Exception as e:
        print(f"❌ Failed to create database pool: {e}")
        raise


async def close_db():
    """Close database connection pool."""
    global _pool
    
    if _pool:
        await _pool.close()
        print("✅ Database pool closed")


async def get_db_pool() -> asyncpg.Pool:
    """Get database connection pool."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


async def get_db_health() -> str:
    """Check database health."""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return "healthy"
    except Exception as e:
        print(f"Database health check failed: {e}")
        return "unhealthy"
