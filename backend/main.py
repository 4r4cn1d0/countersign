"""Main entry point for Agent Observability Platform backend."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.exceptions import RequestValidationError

from api.routes import sessions, events, trace, metrics, health, websocket, research
from services.event_hub import EventHub
from services.archive_service import start_archive_worker, stop_archive_worker
from services.pipeline_worker import start_pipeline_worker, stop_pipeline_worker
from services.realtime_broadcaster import (
    publish_processed_event,
    start_realtime_broadcaster,
    stop_realtime_broadcaster,
)
from services.trace_processor import clear_event_processed_hooks, register_event_processed_hook
from api.middleware import (
    RequestLoggingMiddleware,
    RateLimitMiddleware,
    api_error_handler,
    validation_error_handler,
    generic_error_handler,
    APIError
)
from services.database import init_db, close_db
from services.redis_service import init_redis, close_redis
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # `app` is the FastAPI instance passed by the framework
    """Application lifecycle manager."""
    logger.info("="*60)
    logger.info("🔬 Agent Observability Platform - Starting")
    logger.info("="*60)
    
    # Initialize database connection
    logger.info("📦 Initializing PostgreSQL connection...")
    try:
        await init_db()
        logger.info("✅ PostgreSQL connection established")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        raise
    
    # Initialize Redis connection
    logger.info("📦 Initializing Redis connection...")
    try:
        await init_redis()
        logger.info("✅ Redis connection established")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Redis: {e}")
        raise
    
    app.state.event_hub = EventHub()
    app.state.ws_heartbeat_interval = settings.WS_HEARTBEAT_INTERVAL

    clear_event_processed_hooks()
    register_event_processed_hook(publish_processed_event)

    logger.info("📦 Starting WebSocket broadcaster...")
    await start_realtime_broadcaster(app.state.event_hub)
    logger.info("✅ WebSocket broadcaster running")

    logger.info("📦 Starting trace pipeline worker...")
    await start_pipeline_worker()
    logger.info("✅ Trace pipeline worker running")

    logger.info("📦 Starting archive worker...")
    await start_archive_worker()
    logger.info("✅ Archive worker configured")

    logger.info("✅ All services initialized successfully!")
    logger.info(f"🚀 Server starting on port {settings.PORT}")
    logger.info(f"📝 Debug mode: {settings.DEBUG}")
    logger.info(f"🌐 CORS origins: {', '.join(settings.CORS_ORIGINS)}")
    
    yield
    
    # Cleanup
    logger.info("🛑 Shutting down...")
    await stop_archive_worker()
    await stop_realtime_broadcaster()
    await app.state.event_hub.close()
    await stop_pipeline_worker()
    await close_redis()
    await close_db()
    logger.info("✅ Cleanup complete")


def create_app() -> FastAPI:
    """
    Application factory pattern.
    
    Creates and configures the FastAPI application with:
    - CORS middleware for cross-origin requests
    - Request logging middleware for observability
    - Rate limiting middleware for API protection
    - GZip compression for response optimization
    - Trusted host middleware for security
    - Error handlers for consistent error responses
    
    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Agent Observability Platform API",
        description="Comprehensive monitoring and debugging system for AI agents",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url="/api/redoc" if settings.DEBUG else None,
        openapi_url="/api/openapi.json" if settings.DEBUG else None
    )
    
    # Security: Trusted Host middleware (prevent host header attacks)
    # In production, configure with actual allowed hosts
    if not settings.DEBUG:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["*"]  # Configure with actual hosts in production
        )
    
    # Compression middleware (compress responses > 1KB)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    # CORS middleware (must be added before other middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID", "X-Response-Time", "X-RateLimit-Limit", 
                       "X-RateLimit-Remaining", "X-RateLimit-Reset"]
    )
    
    # Rate limiting middleware (60 requests per minute by default)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=60)
    
    # Request logging middleware
    app.add_middleware(RequestLoggingMiddleware)
    
    # Register error handlers
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)
    
    # Register routes
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(sessions.router, prefix="/api/v1", tags=["sessions"])
    app.include_router(events.router, prefix="/api/v1", tags=["events"])
    app.include_router(trace.router, prefix="/api/v1", tags=["trace"])
    app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
    app.include_router(websocket.router, prefix="/api/v1", tags=["websocket"])
    app.include_router(research.router, prefix="/api/v1", tags=["research"])
    
    logger.info("✅ Application configured successfully")
    logger.info(f"📚 API documentation: http://localhost:{settings.PORT}/api/docs")
    
    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    # Run with uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
        access_log=True
    )
