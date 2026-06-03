"""Tests for FastAPI application structure and configuration."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch


@pytest.fixture
def mock_db_init():
    """Mock database initialization."""
    with patch('services.database.init_db', new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_redis_init():
    """Mock Redis initialization."""
    with patch('services.redis_service.init_redis', new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_db_close():
    """Mock database close."""
    with patch('services.database.close_db', new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_redis_close():
    """Mock Redis close."""
    with patch('services.redis_service.close_redis', new_callable=AsyncMock) as mock:
        yield mock


def test_app_creation(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    """Test that the FastAPI application can be created."""
    from main import create_app
    
    app = create_app()
    
    assert app is not None
    assert app.title == "Agent Observability Platform API"
    assert app.version == "1.0.0"


def test_app_has_cors_middleware(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    """Test that CORS middleware is configured."""
    from main import create_app
    from fastapi.middleware.cors import CORSMiddleware
    
    app = create_app()
    
    # Check if CORS middleware is in the middleware stack
    cors_middleware_found = False
    for middleware in app.user_middleware:
        if middleware.cls == CORSMiddleware:
            cors_middleware_found = True
            break
    
    assert cors_middleware_found, "CORS middleware not found"


def test_app_has_error_handlers(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    """Test that error handlers are registered."""
    from main import create_app
    from api.middleware import APIError
    from fastapi.exceptions import RequestValidationError
    
    app = create_app()
    
    # Check if error handlers are registered
    assert APIError in app.exception_handlers
    assert RequestValidationError in app.exception_handlers
    assert Exception in app.exception_handlers


def test_app_has_routes(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    """Test that all routes are registered."""
    from main import create_app
    
    app = create_app()
    
    # Get all route paths
    routes = [route.path for route in app.routes]
    
    # Check for expected routes
    assert "/api/v1/health" in routes
    assert any("/api/v1/sessions" in route for route in routes)


def test_health_endpoint_structure(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    """Test that health endpoint is accessible."""
    from main import create_app
    
    app = create_app()
    
    # Find health route
    health_routes = [route for route in app.routes if "/health" in route.path]
    
    assert len(health_routes) > 0, "Health endpoint not found"


def test_middleware_order(mock_db_init, mock_redis_init, mock_db_close, mock_redis_close):
    """Test that middleware is added in correct order."""
    from main import create_app
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.middleware.gzip import GZipMiddleware
    from api.middleware import RequestLoggingMiddleware, RateLimitMiddleware
    
    app = create_app()
    
    # Get middleware classes in order
    middleware_classes = [m.cls for m in app.user_middleware]
    
    # CORS should be before other middleware
    assert CORSMiddleware in middleware_classes
    assert GZipMiddleware in middleware_classes
    assert RateLimitMiddleware in middleware_classes
    assert RequestLoggingMiddleware in middleware_classes


def test_api_error_structure():
    """Test APIError exception structure."""
    from api.middleware import APIError
    
    error = APIError(
        message="Test error",
        status_code=400,
        error_code="TEST_ERROR",
        details={"field": "value"}
    )
    
    assert error.message == "Test error"
    assert error.status_code == 400
    assert error.error_code == "TEST_ERROR"
    assert error.details == {"field": "value"}


def test_not_found_error():
    """Test NotFoundError exception."""
    from api.middleware import NotFoundError
    
    error = NotFoundError(resource="Session", identifier="123")
    
    assert error.status_code == 404
    assert error.error_code == "NOT_FOUND"
    assert "Session" in error.message
    assert "123" in error.message


def test_validation_error():
    """Test ValidationError exception."""
    from api.middleware import ValidationError
    
    error = ValidationError(message="Invalid input", details={"field": "email"})
    
    assert error.status_code == 422
    assert error.error_code == "VALIDATION_ERROR"
    assert error.message == "Invalid input"


def test_authentication_error():
    """Test AuthenticationError exception."""
    from api.middleware import AuthenticationError
    
    error = AuthenticationError()
    
    assert error.status_code == 401
    assert error.error_code == "AUTHENTICATION_ERROR"


def test_authorization_error():
    """Test AuthorizationError exception."""
    from api.middleware import AuthorizationError
    
    error = AuthorizationError()
    
    assert error.status_code == 403
    assert error.error_code == "AUTHORIZATION_ERROR"


def test_rate_limit_error():
    """Test RateLimitError exception."""
    from api.middleware import RateLimitError
    
    error = RateLimitError()
    
    assert error.status_code == 429
    assert error.error_code == "RATE_LIMIT_EXCEEDED"


def test_service_unavailable_error():
    """Test ServiceUnavailableError exception."""
    from api.middleware import ServiceUnavailableError
    
    error = ServiceUnavailableError(service="database")
    
    assert error.status_code == 503
    assert error.error_code == "SERVICE_UNAVAILABLE"
    assert "database" in error.message
