"""Middleware package for FastAPI application."""

from api.middleware.auth import get_current_user, require_permission, get_optional_user
from api.middleware.error_handlers import (
    APIError,
    NotFoundError,
    ValidationError,
    AuthenticationError,
    AuthorizationError,
    RateLimitError,
    ServiceUnavailableError,
    api_error_handler,
    validation_error_handler,
    generic_error_handler
)
from api.middleware.logging import RequestLoggingMiddleware
from api.middleware.rate_limit import RateLimitMiddleware

__all__ = [
    # Auth
    "get_current_user",
    "require_permission",
    "get_optional_user",
    # Error handlers
    "APIError",
    "NotFoundError",
    "ValidationError",
    "AuthenticationError",
    "AuthorizationError",
    "RateLimitError",
    "ServiceUnavailableError",
    "api_error_handler",
    "validation_error_handler",
    "generic_error_handler",
    # Middleware
    "RequestLoggingMiddleware",
    "RateLimitMiddleware",
]
