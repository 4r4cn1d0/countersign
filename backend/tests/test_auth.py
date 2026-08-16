"""Tests for authentication and authorization system."""

from datetime import datetime, timedelta
from services.auth import AuthService, PermissionModel, TokenData


class TestAPIKeyGeneration:
    """Test API key generation and validation."""
    
    def test_generate_api_key_format(self):
        """Test that generated API keys have correct format."""
        plain_key, key_hash = AuthService.generate_api_key()
        
        # Check plain key format
        assert plain_key.startswith("gb_")
        assert len(plain_key) > 10
        
        # Check hash is different from plain key
        assert key_hash != plain_key
        assert len(key_hash) > 0
    
    def test_generate_api_key_uniqueness(self):
        """Test that generated API keys are unique."""
        key1, hash1 = AuthService.generate_api_key()
        key2, hash2 = AuthService.generate_api_key()
        
        assert key1 != key2
        assert hash1 != hash2
    
    def test_verify_api_key_valid(self):
        """Test verification of valid API key."""
        plain_key, key_hash = AuthService.generate_api_key()
        
        assert AuthService.verify_api_key(plain_key, key_hash) is True
    
    def test_verify_api_key_invalid(self):
        """Test verification of invalid API key."""
        plain_key, key_hash = AuthService.generate_api_key()
        wrong_key = "gb_wrong_key"
        
        assert AuthService.verify_api_key(wrong_key, key_hash) is False
    
    def test_verify_api_key_malformed_hash(self):
        """Test verification with malformed hash."""
        plain_key = "gb_test_key"
        malformed_hash = "not_a_valid_hash"
        
        assert AuthService.verify_api_key(plain_key, malformed_hash) is False


class TestJWTTokens:
    """Test JWT token creation and verification."""
    
    def test_create_jwt_token(self):
        """Test JWT token creation."""
        user_id = "user_123"
        permissions = ["session:read", "session:create"]
        
        token = AuthService.create_jwt_token(user_id, permissions)
        
        assert isinstance(token, str)
        assert len(token) > 0
        # JWT tokens have 3 parts separated by dots
        assert token.count('.') == 2
    
    def test_verify_jwt_token_valid(self):
        """Test verification of valid JWT token."""
        user_id = "user_123"
        permissions = ["session:read", "session:create"]
        
        token = AuthService.create_jwt_token(user_id, permissions)
        token_data = AuthService.verify_jwt_token(token)
        
        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.permissions == permissions
        assert isinstance(token_data.exp, datetime)
    
    def test_verify_jwt_token_invalid(self):
        """Test verification of invalid JWT token."""
        invalid_token = "invalid.token.here"
        
        token_data = AuthService.verify_jwt_token(invalid_token)
        
        assert token_data is None
    
    def test_jwt_token_expiration(self):
        """Test JWT token with custom expiration."""
        user_id = "user_123"
        permissions = ["session:read"]
        
        # Create token with short expiration
        short_expires = timedelta(minutes=5)
        token_short = AuthService.create_jwt_token(user_id, permissions, short_expires)
        data_short = AuthService.verify_jwt_token(token_short)
        
        # Create token with long expiration
        long_expires = timedelta(hours=2)
        token_long = AuthService.create_jwt_token(user_id, permissions, long_expires)
        data_long = AuthService.verify_jwt_token(token_long)
        
        # Verify both tokens are valid
        assert data_short is not None
        assert data_long is not None
        
        # Verify long token expires after short token
        assert data_long.exp > data_short.exp
    
    def test_jwt_token_expired(self):
        """Test verification of expired JWT token."""
        user_id = "user_123"
        permissions = ["session:read"]
        # Create token that expires immediately
        expires_delta = timedelta(seconds=-1)
        
        token = AuthService.create_jwt_token(user_id, permissions, expires_delta)
        token_data = AuthService.verify_jwt_token(token)
        
        # Expired tokens should be rejected
        assert token_data is None
    
    def test_jwt_token_different_users(self):
        """Test that tokens for different users are different."""
        token1 = AuthService.create_jwt_token("user_1", ["session:read"])
        token2 = AuthService.create_jwt_token("user_2", ["session:read"])
        
        assert token1 != token2
        
        data1 = AuthService.verify_jwt_token(token1)
        data2 = AuthService.verify_jwt_token(token2)
        
        assert data1.user_id != data2.user_id


class TestPermissions:
    """Test permission checking."""
    
    def test_check_permission_has_permission(self):
        """Test permission check when user has permission."""
        required = "session:read"
        user_permissions = ["session:read", "session:create"]
        
        assert AuthService.check_permission(required, user_permissions) is True
    
    def test_check_permission_no_permission(self):
        """Test permission check when user lacks permission."""
        required = "session:delete"
        user_permissions = ["session:read", "session:create"]
        
        assert AuthService.check_permission(required, user_permissions) is False
    
    def test_check_permission_admin_has_all(self):
        """Test that admin permission grants all permissions."""
        required = "session:delete"
        user_permissions = ["admin"]
        
        assert AuthService.check_permission(required, user_permissions) is True
    
    def test_check_permission_empty_permissions(self):
        """Test permission check with empty permissions."""
        required = "session:read"
        user_permissions = []
        
        assert AuthService.check_permission(required, user_permissions) is False


class TestResourceOwnership:
    """Test resource ownership checks."""
    
    def test_check_resource_ownership_owner(self):
        """Test resource access by owner."""
        user_id = "user_123"
        resource_user_id = "user_123"
        permissions = ["session:read"]
        
        assert AuthService.check_resource_ownership(
            user_id, resource_user_id, permissions
        ) is True
    
    def test_check_resource_ownership_not_owner(self):
        """Test resource access by non-owner."""
        user_id = "user_123"
        resource_user_id = "user_456"
        permissions = ["session:read"]
        
        assert AuthService.check_resource_ownership(
            user_id, resource_user_id, permissions
        ) is False
    
    def test_check_resource_ownership_admin(self):
        """Test resource access by admin."""
        user_id = "user_123"
        resource_user_id = "user_456"
        permissions = ["admin"]
        
        assert AuthService.check_resource_ownership(
            user_id, resource_user_id, permissions
        ) is True


class TestPermissionModel:
    """Test permission model definitions."""
    
    def test_permission_constants(self):
        """Test that permission constants are defined."""
        assert hasattr(PermissionModel, 'SESSION_CREATE')
        assert hasattr(PermissionModel, 'SESSION_READ')
        assert hasattr(PermissionModel, 'SESSION_UPDATE')
        assert hasattr(PermissionModel, 'SESSION_DELETE')
        assert hasattr(PermissionModel, 'EVENT_CREATE')
        assert hasattr(PermissionModel, 'EVENT_READ')
        assert hasattr(PermissionModel, 'METRICS_READ')
        assert hasattr(PermissionModel, 'ALERT_CREATE')
        assert hasattr(PermissionModel, 'ALERT_READ')
        assert hasattr(PermissionModel, 'ALERT_UPDATE')
        assert hasattr(PermissionModel, 'ALERT_DELETE')
        assert hasattr(PermissionModel, 'ADMIN')
    
    def test_get_default_permissions(self):
        """Test default permissions for new users."""
        default_perms = PermissionModel.get_default_permissions()
        
        assert isinstance(default_perms, list)
        assert len(default_perms) > 0
        assert PermissionModel.SESSION_CREATE in default_perms
        assert PermissionModel.SESSION_READ in default_perms
        assert PermissionModel.EVENT_CREATE in default_perms
        assert PermissionModel.EVENT_READ in default_perms
        # Admin should not be in default permissions
        assert PermissionModel.ADMIN not in default_perms


class TestTokenData:
    """Test TokenData model."""
    
    def test_token_data_creation(self):
        """Test TokenData model creation."""
        exp = datetime.utcnow() + timedelta(hours=1)
        token_data = TokenData(
            user_id="user_123",
            permissions=["session:read"],
            exp=exp
        )
        
        assert token_data.user_id == "user_123"
        assert token_data.permissions == ["session:read"]
        assert token_data.exp == exp


class TestIntegration:
    """Integration tests for authentication flow."""
    
    def test_full_api_key_flow(self):
        """Test complete API key generation and verification flow."""
        # Generate key
        plain_key, key_hash = AuthService.generate_api_key()
        
        # Verify correct key
        assert AuthService.verify_api_key(plain_key, key_hash) is True
        
        # Verify wrong key
        wrong_key = "gb_wrong_key"
        assert AuthService.verify_api_key(wrong_key, key_hash) is False
    
    def test_full_jwt_flow(self):
        """Test complete JWT token creation and verification flow."""
        # Create token
        user_id = "user_123"
        permissions = ["session:read", "session:create"]
        token = AuthService.create_jwt_token(user_id, permissions)
        
        # Verify token
        token_data = AuthService.verify_jwt_token(token)
        assert token_data is not None
        assert token_data.user_id == user_id
        
        # Check permissions
        assert AuthService.check_permission("session:read", token_data.permissions) is True
        assert AuthService.check_permission("session:delete", token_data.permissions) is False
        
        # Check resource ownership
        assert AuthService.check_resource_ownership(
            user_id, user_id, token_data.permissions
        ) is True
        assert AuthService.check_resource_ownership(
            user_id, "other_user", token_data.permissions
        ) is False
    
    def test_admin_full_access(self):
        """Test that admin has full access to all resources and permissions."""
        # Create admin token
        admin_id = "admin_123"
        admin_permissions = ["admin"]
        token = AuthService.create_jwt_token(admin_id, admin_permissions)
        
        # Verify token
        token_data = AuthService.verify_jwt_token(token)
        assert token_data is not None
        
        # Admin should have all permissions
        assert AuthService.check_permission("session:read", token_data.permissions) is True
        assert AuthService.check_permission("session:delete", token_data.permissions) is True
        assert AuthService.check_permission("any:permission", token_data.permissions) is True
        
        # Admin should access all resources
        assert AuthService.check_resource_ownership(
            admin_id, "user_1", token_data.permissions
        ) is True
        assert AuthService.check_resource_ownership(
            admin_id, "user_2", token_data.permissions
        ) is True
