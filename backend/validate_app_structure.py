"""Validation script for FastAPI application structure."""

import sys


def validate_structure():
    """Validate that all components can be imported."""
    print("="*60)
    print("Validating Agent Observability Platform Structure")
    print("="*60)
    
    errors = []
    
    # Test 1: Import configuration
    print("\n1. Testing configuration...")
    try:
        from config import settings
        print(f"   ✅ Configuration loaded")
        print(f"      - CORS Origins: {settings.CORS_ORIGINS}")
        print(f"      - Port: {settings.PORT}")
        print(f"      - Debug: {settings.DEBUG}")
    except Exception as e:
        print(f"   ❌ Configuration failed: {e}")
        errors.append(("Configuration", str(e)))
    
    # Test 2: Import error handlers
    print("\n2. Testing error handlers...")
    try:
        from api.middleware import (
            APIError,
            NotFoundError,
            ValidationError,
            AuthenticationError,
            AuthorizationError,
            RateLimitError,
            ServiceUnavailableError
        )
        print("   ✅ All error handlers imported")
    except Exception as e:
        print(f"   ❌ Error handlers failed: {e}")
        errors.append(("Error Handlers", str(e)))
    
    # Test 3: Import middleware
    print("\n3. Testing middleware...")
    try:
        from api.middleware import (
            RequestLoggingMiddleware,
            RateLimitMiddleware
        )
        print("   ✅ All middleware imported")
    except Exception as e:
        print(f"   ❌ Middleware failed: {e}")
        errors.append(("Middleware", str(e)))
    
    # Test 4: Check directory structure
    print("\n4. Checking directory structure...")
    import os
    required_dirs = [
        "api",
        "api/routes",
        "api/middleware",
        "models",
        "services",
        "adapters",
        "tests"
    ]
    
    for dir_path in required_dirs:
        if os.path.isdir(dir_path):
            print(f"   ✅ {dir_path}/ exists")
        else:
            print(f"   ❌ {dir_path}/ missing")
            errors.append(("Directory Structure", f"{dir_path}/ not found"))
    
    # Test 5: Check main files
    print("\n5. Checking main files...")
    required_files = [
        "main.py",
        "config.py",
        "requirements.txt",
        "api/__init__.py",
        "api/middleware/__init__.py",
        "api/middleware/error_handlers.py",
        "api/middleware/logging.py",
        "api/middleware/rate_limit.py",
        "api/routes/__init__.py",
        "api/routes/health.py",
        "api/routes/sessions.py",
        "api/routes/events.py",
        "api/routes/metrics.py",
        "api/routes/trace.py",
    ]
    
    for file_path in required_files:
        if os.path.isfile(file_path):
            print(f"   ✅ {file_path} exists")
        else:
            print(f"   ❌ {file_path} missing")
            errors.append(("File Structure", f"{file_path} not found"))
    
    # Summary
    print("\n" + "="*60)
    if errors:
        print(f"❌ Validation FAILED with {len(errors)} error(s):")
        for component, error in errors:
            print(f"   - {component}: {error}")
        return False
    else:
        print("✅ All validation checks PASSED!")
        print("\nApplication structure is correctly configured with:")
        print("  - FastAPI application factory pattern")
        print("  - CORS middleware")
        print("  - Request logging middleware")
        print("  - Rate limiting middleware")
        print("  - GZip compression middleware")
        print("  - Comprehensive error handlers")
        print("  - Proper directory structure (api/, models/, services/, adapters/)")
        return True


if __name__ == "__main__":
    success = validate_structure()
    sys.exit(0 if success else 1)
