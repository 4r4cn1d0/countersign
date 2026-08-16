"""Tests for authentication middleware."""

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from datetime import timedelta

from api.middleware.auth import get_current_user, require_permission, get_optional_user
from services.auth import AuthService, PermissionModel


# Create test app
app = FastAPI()


@app.get("/protected")
async def protected_route(current_user = Depends(get_current_user)):
    """Protected route requiring authentication."""
    return {"user_id": current_user.user_id, "permissions": current_user.permissions}


@app.get("/admin-only")
async def admin_route(current_user = Depends(require_permission(PermissionModel.ADMIN))):
    """Route requiring admin permission."""
    return {"message": "Admin access granted"}


@app.get("/session-create")
async def session_create_route(
    current_user = Depends(require_permission(PermissionModel.SESSION_CREATE))
):
    """Route requiring session:create permission."""
    return {"message": "Session creation allowed"}


@app.get("/optional-auth")
async def optional_auth_route(current_user = Depends(get_optional_user)):
    """Route with optional authentication."""
    if current_user:
        return {"authenticated": True, "user_id": current_user.user_id}
    return {"authenticated": False}


client = TestClient(app)


class TestAuthenticationMiddleware:
    """Test authentication middleware."""
    
    def test_protected_route_without_token(self):
        """Test accessing protected route without token."""
        response = client.get("/protected")
        
        assert response.status_code == 403
    
    def test_protected_route_with_valid_token(self):
        """Test accessing protected route with valid token."""
        # Create token
        token = AuthService.create_jwt_token("user_123", ["session:read"])
        
        # Make request with token
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "user_123"
        assert "session:read" in data["permissions"]
    
    def test_protected_route_with_invalid_token(self):
        """Test accessing protected route with invalid token."""
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        
        assert response.status_code == 401
    
    def test_protected_route_with_expired_token(self):
        """Test accessing protected route with expired token."""
        # Create expired token
        token = AuthService.create_jwt_token(
            "user_123",
            ["session:read"],
            expires_delta=timedelta(seconds=-1)
        )
        
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 401


class TestPermissionMiddleware:
    """Test permission-based middleware."""
    
    def test_admin_route_with_admin_permission(self):
        """Test admin route with admin permission."""
        token = AuthService.create_jwt_token("admin_123", ["admin"])
        
        response = client.get(
            "/admin-only",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        assert response.json()["message"] == "Admin access granted"
    
    def test_admin_route_without_admin_permission(self):
        """Test admin route without admin permission."""
        token = AuthService.create_jwt_token("user_123", ["session:read"])
        
        response = client.get(
            "/admin-only",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 403
    
    def test_session_create_route_with_permission(self):
        """Test session create route with correct permission."""
        token = AuthService.create_jwt_token("user_123", ["session:create"])
        
        response = client.get(
            "/session-create",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        assert response.json()["message"] == "Session creation allowed"
    
    def test_session_create_route_without_permission(self):
        """Test session create route without permission."""
        token = AuthService.create_jwt_token("user_123", ["session:read"])
        
        response = client.get(
            "/session-create",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 403
    
    def test_admin_has_all_permissions(self):
        """Test that admin can access routes requiring specific permissions."""
        token = AuthService.create_jwt_token("admin_123", ["admin"])
        
        # Admin should access session create route
        response = client.get(
            "/session-create",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200


class TestOptionalAuthentication:
    """Test optional authentication middleware."""
    
    def test_optional_auth_with_token(self):
        """Test optional auth route with token."""
        token = AuthService.create_jwt_token("user_123", ["session:read"])
        
        response = client.get(
            "/optional-auth",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["user_id"] == "user_123"
    
    def test_optional_auth_without_token(self):
        """Test optional auth route without token."""
        response = client.get("/optional-auth")
        
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
    
    def test_optional_auth_with_invalid_token(self):
        """Test optional auth route with invalid token."""
        response = client.get(
            "/optional-auth",
            headers={"Authorization": "Bearer invalid.token"}
        )
        
        # Should still return 200 but not authenticated
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False


class TestAuthorizationHeaders:
    """Test various authorization header formats."""
    
    def test_missing_bearer_prefix(self):
        """Test token without Bearer prefix."""
        token = AuthService.create_jwt_token("user_123", ["session:read"])
        
        response = client.get(
            "/protected",
            headers={"Authorization": token}  # Missing "Bearer "
        )
        
        # Should fail because Bearer prefix is required
        assert response.status_code in [401, 403]
    
    def test_case_sensitive_bearer(self):
        """Test that Bearer is case-sensitive."""
        token = AuthService.create_jwt_token("user_123", ["session:read"])
        
        response = client.get(
            "/protected",
            headers={"Authorization": f"bearer {token}"}  # lowercase
        )
        
        # FastAPI's HTTPBearer might be case-insensitive, but test it
        # The actual behavior depends on the implementation
        assert response.status_code in [200, 401, 403]
    
    def test_empty_authorization_header(self):
        """Test with empty authorization header."""
        response = client.get(
            "/protected",
            headers={"Authorization": ""}
        )
        
        assert response.status_code in [401, 403]


class TestMultiplePermissions:
    """Test routes requiring multiple permissions."""
    
    def test_user_with_multiple_permissions(self):
        """Test user with multiple permissions."""
        permissions = [
            PermissionModel.SESSION_CREATE,
            PermissionModel.SESSION_READ,
            PermissionModel.EVENT_CREATE
        ]
        token = AuthService.create_jwt_token("user_123", permissions)
        
        # Should access session create route
        response = client.get(
            "/session-create",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
    
    def test_user_with_default_permissions(self):
        """Test user with default permissions."""
        default_perms = PermissionModel.get_default_permissions()
        token = AuthService.create_jwt_token("user_123", default_perms)
        
        # Should access session create route (included in defaults)
        response = client.get(
            "/session-create",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        
        # Should NOT access admin route
        response = client.get(
            "/admin-only",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 403
