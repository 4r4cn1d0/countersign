"""Authentication and authorization service."""

import secrets
import bcrypt
import os
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from jose import JWTError, jwt
from pydantic import BaseModel

from config import settings


class APIKey(BaseModel):
    """API key model."""
    
    key_id: str
    key_hash: str
    user_id: str
    name: str
    permissions: list[str]
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class TokenData(BaseModel):
    """JWT token data."""
    
    user_id: str
    permissions: list[str]
    exp: datetime


class AuthService:
    """Authentication and authorization service."""
    
    _private_key: Optional[str] = None
    _public_key: Optional[str] = None
    
    @classmethod
    def _load_keys(cls):
        """Load RSA keys for JWT signing."""
        if cls._private_key is None or cls._public_key is None:
            # Load private key
            if os.path.exists(settings.JWT_PRIVATE_KEY_PATH):
                with open(settings.JWT_PRIVATE_KEY_PATH, 'r') as f:
                    cls._private_key = f.read()
            else:
                raise FileNotFoundError(
                    f"JWT private key not found at {settings.JWT_PRIVATE_KEY_PATH}. "
                    "Run generate_keys.py to create RSA key pair."
                )
            
            # Load public key
            if os.path.exists(settings.JWT_PUBLIC_KEY_PATH):
                with open(settings.JWT_PUBLIC_KEY_PATH, 'r') as f:
                    cls._public_key = f.read()
            else:
                raise FileNotFoundError(
                    f"JWT public key not found at {settings.JWT_PUBLIC_KEY_PATH}. "
                    "Run generate_keys.py to create RSA key pair."
                )
    
    @staticmethod
    def generate_api_key() -> tuple[str, str]:
        """
        Generate a new API key.
        
        Returns:
            Tuple of (plain_key, key_hash)
        """
        # Generate random key with prefix
        plain_key = f"gb_{secrets.token_urlsafe(32)}"
        
        # Hash the key for storage
        key_hash = bcrypt.hashpw(
            plain_key.encode(),
            bcrypt.gensalt(rounds=settings.API_KEY_HASH_ROUNDS)
        ).decode()
        
        return plain_key, key_hash
    
    @staticmethod
    def verify_api_key(plain_key: str, key_hash: str) -> bool:
        """
        Verify an API key against its hash.
        
        Args:
            plain_key: Plain text API key
            key_hash: Hashed API key from database
            
        Returns:
            True if key is valid
        """
        try:
            return bcrypt.checkpw(
                plain_key.encode(),
                key_hash.encode()
            )
        except Exception:
            return False
    
    @classmethod
    def create_jwt_token(
        cls,
        user_id: str,
        permissions: list[str],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create a JWT token using RS256 algorithm.
        
        Args:
            user_id: User identifier
            permissions: List of permissions
            expires_delta: Token expiration time
            
        Returns:
            Encoded JWT token
        """
        cls._load_keys()
        
        if expires_delta is None:
            expires_delta = timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
        
        expire = datetime.utcnow() + expires_delta
        
        payload = {
            "user_id": user_id,
            "permissions": permissions,
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": str(uuid4())
        }
        
        encoded_jwt = jwt.encode(
            payload,
            cls._private_key,
            algorithm=settings.JWT_ALGORITHM
        )
        
        return encoded_jwt
    
    @classmethod
    def verify_jwt_token(cls, token: str) -> Optional[TokenData]:
        """
        Verify and decode a JWT token using RS256 algorithm.
        
        Args:
            token: JWT token string
            
        Returns:
            TokenData if valid, None otherwise
        """
        try:
            cls._load_keys()
            
            payload = jwt.decode(
                token,
                cls._public_key,
                algorithms=[settings.JWT_ALGORITHM]
            )
            
            user_id = payload.get("user_id")
            permissions = payload.get("permissions", [])
            exp = datetime.fromtimestamp(payload.get("exp"))
            
            if user_id is None:
                return None
            
            return TokenData(
                user_id=user_id,
                permissions=permissions,
                exp=exp
            )
        
        except JWTError:
            return None
    
    @staticmethod
    def check_permission(
        required_permission: str,
        user_permissions: list[str]
    ) -> bool:
        """
        Check if user has required permission.
        
        Args:
            required_permission: Permission to check
            user_permissions: User's permissions
            
        Returns:
            True if user has permission
        """
        # Admin has all permissions
        if "admin" in user_permissions:
            return True
        
        # Check specific permission
        return required_permission in user_permissions
    
    @staticmethod
    def check_resource_ownership(
        user_id: str,
        resource_user_id: str,
        user_permissions: list[str]
    ) -> bool:
        """
        Check if user owns a resource or has admin permission.
        
        Args:
            user_id: Current user ID
            resource_user_id: Resource owner ID
            user_permissions: User's permissions
            
        Returns:
            True if user can access resource
        """
        # Admin can access all resources
        if "admin" in user_permissions:
            return True
        
        # User can access their own resources
        return user_id == resource_user_id


class PermissionModel:
    """Permission definitions."""
    
    # Session permissions
    SESSION_CREATE = "session:create"
    SESSION_READ = "session:read"
    SESSION_UPDATE = "session:update"
    SESSION_DELETE = "session:delete"
    
    # Event permissions
    EVENT_CREATE = "event:create"
    EVENT_READ = "event:read"
    
    # Metrics permissions
    METRICS_READ = "metrics:read"
    
    # Alert permissions
    ALERT_CREATE = "alert:create"
    ALERT_READ = "alert:read"
    ALERT_UPDATE = "alert:update"
    ALERT_DELETE = "alert:delete"
    
    # Admin permission
    ADMIN = "admin"
    
    @classmethod
    def get_default_permissions(cls) -> list[str]:
        """Get default permissions for new users."""
        return [
            cls.SESSION_CREATE,
            cls.SESSION_READ,
            cls.EVENT_CREATE,
            cls.EVENT_READ,
            cls.METRICS_READ,
            cls.ALERT_CREATE,
            cls.ALERT_READ,
            cls.ALERT_UPDATE,
            cls.ALERT_DELETE,
        ]
