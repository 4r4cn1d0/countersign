"""Rate limiting middleware for FastAPI application."""

import time
from typing import Callable, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict
import asyncio

from api.middleware.error_handlers import RateLimitError


class RateLimiter:
    """
    Simple in-memory rate limiter using sliding window.
    
    For production, use Redis-based rate limiting.
    """
    
    def __init__(self, requests_per_minute: int = 60):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_minute: Maximum requests per minute per client
        """
        self.requests_per_minute = requests_per_minute
        self.window_size = 60  # seconds
        self.requests = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def is_allowed(self, client_id: str) -> bool:
        """
        Check if request is allowed for client.
        
        Args:
            client_id: Client identifier (IP address or user ID)
            
        Returns:
            True if request is allowed, False otherwise
        """
        async with self._lock:
            now = time.time()
            
            # Remove old requests outside the window
            self.requests[client_id] = [
                req_time for req_time in self.requests[client_id]
                if now - req_time < self.window_size
            ]
            
            # Check if limit exceeded
            if len(self.requests[client_id]) >= self.requests_per_minute:
                return False
            
            # Add current request
            self.requests[client_id].append(now)
            return True
    
    async def get_remaining(self, client_id: str) -> int:
        """
        Get remaining requests for client.
        
        Args:
            client_id: Client identifier
            
        Returns:
            Number of remaining requests
        """
        async with self._lock:
            now = time.time()
            
            # Remove old requests
            self.requests[client_id] = [
                req_time for req_time in self.requests[client_id]
                if now - req_time < self.window_size
            ]
            
            return max(0, self.requests_per_minute - len(self.requests[client_id]))
    
    async def get_reset_time(self, client_id: str) -> Optional[float]:
        """
        Get time when rate limit resets for client.
        
        Args:
            client_id: Client identifier
            
        Returns:
            Unix timestamp when limit resets, or None if no requests
        """
        async with self._lock:
            if not self.requests[client_id]:
                return None
            
            oldest_request = min(self.requests[client_id])
            return oldest_request + self.window_size


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce rate limits on API requests.
    """
    
    def __init__(self, app, requests_per_minute: int = 60):
        """
        Initialize rate limit middleware.
        
        Args:
            app: FastAPI application
            requests_per_minute: Maximum requests per minute per client
        """
        super().__init__(app)
        self.rate_limiter = RateLimiter(requests_per_minute)
    
    def _get_client_id(self, request: Request) -> str:
        """
        Get client identifier from request.
        
        Args:
            request: FastAPI request
            
        Returns:
            Client identifier (user ID or IP address)
        """
        # Try to get user ID from request state (set by auth middleware)
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"
        
        # Fall back to IP address
        if request.client:
            return f"ip:{request.client.host}"
        
        return "unknown"
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Check rate limit and process request.
        
        Args:
            request: FastAPI request
            call_next: Next middleware/route handler
            
        Returns:
            Response from route handler
            
        Raises:
            RateLimitError: If rate limit exceeded
        """
        # Skip rate limiting for health check
        if request.url.path == "/api/v1/health":
            return await call_next(request)
        
        client_id = self._get_client_id(request)
        
        # Check rate limit
        if not await self.rate_limiter.is_allowed(client_id):
            reset_time = await self.rate_limiter.get_reset_time(client_id)
            raise RateLimitError(
                message=f"Rate limit exceeded. Try again in {int(reset_time - time.time())} seconds."
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        remaining = await self.rate_limiter.get_remaining(client_id)
        reset_time = await self.rate_limiter.get_reset_time(client_id)
        
        response.headers["X-RateLimit-Limit"] = str(self.rate_limiter.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        if reset_time:
            response.headers["X-RateLimit-Reset"] = str(int(reset_time))
        
        return response
