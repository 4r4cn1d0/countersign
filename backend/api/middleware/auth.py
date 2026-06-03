"""Authentication middleware for FastAPI."""

from typing import Optional
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from services.auth import AuthService, TokenData, PermissionModel


security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> TokenData:
    """
    Get current authenticated user from JWT token.
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        TokenData with user information
        
    Raises:
        HTTPException: If token is invalid
    """
    token = credentials.credentials
    
    token_data = AuthService.verify_jwt_token(token)
    
    if token_data is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token_data


def require_permission(permission: str):
    """
    Dependency factory to require specific permission.
    
    Args:
        permission: Required permission
        
    Returns:
        Dependency function
    """
    def permission_checker(
        current_user: TokenData = Depends(get_current_user)
    ) -> TokenData:
        if not AuthService.check_permission(permission, current_user.permissions):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {permission} required"
            )
        return current_user
    
    return permission_checker


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(optional_security)
) -> Optional[TokenData]:
    """
    Get current user if authenticated, None otherwise.
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        TokenData if authenticated, None otherwise
    """
    if credentials is None:
        return None
    
    token = credentials.credentials
    return AuthService.verify_jwt_token(token)
