"""Configuration for Agent Observability Platform."""

from pathlib import Path
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def parse_cors_origins(v: str) -> List[str]:
    """Parse CORS_ORIGINS from comma-separated string."""
    if not v:
        return [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    return [origin.strip() for origin in v.split(',')]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    APP_NAME: str = "Agent Observability Platform"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    PORT: int = 8000
    
    # CORS
    CORS_ORIGINS_STR: str = Field(
        default="http://localhost:3000,http://localhost:3001,http://localhost:5173,http://127.0.0.1:5173",
        validation_alias="CORS_ORIGINS",
    )
    
    # Database (PostgreSQL + TimescaleDB)
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/agent_observability"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_SIZE: int = 10
    
    # Redis Streams
    REDIS_STREAM_NAME: str = "trace_events"
    REDIS_CONSUMER_GROUP: str = "processors"
    REDIS_CONSUMER_NAME: str = "processor_1"
    REDIS_PROCESSED_STREAM_NAME: str = "processed_trace_events"
    REDIS_BROADCASTER_GROUP: str = "websocket_broadcasters"
    REDIS_BROADCASTER_NAME: str = "broadcaster_1"
    
    # Authentication
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "RS256"
    JWT_EXPIRATION_MINUTES: int = 60
    JWT_PRIVATE_KEY_PATH: str = str(BASE_DIR / "keys" / "jwt_private.pem")
    JWT_PUBLIC_KEY_PATH: str = str(BASE_DIR / "keys" / "jwt_public.pem")
    API_KEY_HASH_ROUNDS: int = 12
    
    # Storage
    S3_BUCKET: str = "agent-observability-archives"
    S3_ENDPOINT: str = ""  # Leave empty for AWS S3
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    
    # Retention
    HOT_STORAGE_DAYS: int = 30
    WARM_STORAGE_DAYS: int = 90
    ARCHIVE_ENABLED: bool = True
    ARCHIVE_INTERVAL_SECONDS: int = 3600
    
    # Processing
    BATCH_SIZE: int = 100
    PROCESSING_WORKERS: int = 4
    
    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30
    WS_MAX_CONNECTIONS: int = 1000
    WS_CLIENT_BUFFER_SIZE: int = 100
    WS_BATCH_MAX_SIZE: int = 20
    WS_BATCH_WINDOW_MS: int = 20
    
    @property
    def CORS_ORIGINS(self) -> List[str]:
        """Get CORS origins as a list."""
        return parse_cors_origins(self.CORS_ORIGINS_STR)
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra='ignore'  # Ignore extra fields from .env
    )


settings = Settings()
