"""Health check endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.database import get_db_health
from services.redis_service import get_redis_health


router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    database: str
    redis: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        HealthResponse with status of all services
    """
    db_status = await get_db_health()
    redis_status = await get_redis_health()
    
    overall_status = "healthy" if db_status == "healthy" and redis_status == "healthy" else "unhealthy"
    
    if overall_status == "unhealthy":
        raise HTTPException(status_code=503, detail="Service unhealthy")
    
    return HealthResponse(
        status=overall_status,
        database=db_status,
        redis=redis_status,
        version="1.0.0"
    )
