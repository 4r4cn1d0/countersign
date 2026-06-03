# Authentication and Authorization System

## Overview

The Agent Memory Observatory uses a robust authentication and authorization system with:
- **API Keys**: For programmatic access and SDK authentication
- **JWT Tokens (RS256)**: For user sessions and WebSocket connections
- **Permission-Based Access Control**: Granular permissions for different operations
- **Resource Ownership**: Users can only access their own resources (unless admin)

## Quick Start

### 1. Generate RSA Keys

Before running the application, generate RSA key pair for JWT signing:

```bash
cd backend
python generate_keys.py
```

This creates:
- `keys/jwt_private.pem` - Private key for signing tokens
- `keys/jwt_public.pem` - Public key for verifying tokens

⚠️ **Important**: Keep the private key secure and never commit it to version control!

### 2. Configure Environment

Set authentication settings in `.env`:

```env
# JWT Configuration
JWT_EXPIRATION_MINUTES=60
JWT_PRIVATE_KEY_PATH=keys/jwt_private.pem
JWT_PUBLIC_KEY_PATH=keys/jwt_public.pem
JWT_ALGORITHM=RS256

# API Key Configuration
API_KEY_HASH_ROUNDS=12
```

## API Keys

### Generating API Keys

```python
from services.auth import AuthService

# Generate new API key
plain_key, key_hash = AuthService.generate_api_key()

# plain_key: "gb_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
# key_hash: bcrypt hash for storage

# Store key_hash in database
# Give plain_key to user (only shown once!)
```

### Verifying API Keys

```python
from services.auth import AuthService

# Verify API key
is_valid = AuthService.verify_api_key(plain_key, key_hash)
```

### API Key Format

- Prefix: `gb_`
- Length: 43 characters (prefix + 40 character token)
- Example: `gb_1234567890abcdefghijklmnopqrstuvwxyz1234`

## JWT Tokens

### Creating Tokens

```python
from services.auth import AuthService, PermissionModel
from datetime import timedelta

# Create token with default expiration (60 minutes)
token = AuthService.create_jwt_token(
    user_id="user_123",
    permissions=[
        PermissionModel.SESSION_CREATE,
        PermissionModel.SESSION_READ,
        PermissionModel.EVENT_CREATE
    ]
)

# Create token with custom expiration
token = AuthService.create_jwt_token(
    user_id="user_123",
    permissions=["session:read"],
    expires_delta=timedelta(hours=2)
)
```

### Verifying Tokens

```python
from services.auth import AuthService

# Verify and decode token
token_data = AuthService.verify_jwt_token(token)

if token_data:
    print(f"User ID: {token_data.user_id}")
    print(f"Permissions: {token_data.permissions}")
    print(f"Expires: {token_data.exp}")
else:
    print("Invalid or expired token")
```

### Token Structure

JWT tokens contain:
- `user_id`: User identifier
- `permissions`: List of permission strings
- `exp`: Expiration timestamp
- `iat`: Issued-at timestamp
- `jti`: Unique token ID

## Permissions

### Available Permissions

```python
from services.auth import PermissionModel

# Session permissions
PermissionModel.SESSION_CREATE   # "session:create"
PermissionModel.SESSION_READ     # "session:read"
PermissionModel.SESSION_UPDATE   # "session:update"
PermissionModel.SESSION_DELETE   # "session:delete"

# Event permissions
PermissionModel.EVENT_CREATE     # "event:create"
PermissionModel.EVENT_READ       # "event:read"

# Metrics permissions
PermissionModel.METRICS_READ     # "metrics:read"

# Alert permissions
PermissionModel.ALERT_CREATE     # "alert:create"
PermissionModel.ALERT_READ       # "alert:read"
PermissionModel.ALERT_UPDATE     # "alert:update"
PermissionModel.ALERT_DELETE     # "alert:delete"

# Admin permission (grants all permissions)
PermissionModel.ADMIN            # "admin"
```

### Checking Permissions

```python
from services.auth import AuthService

# Check if user has permission
has_permission = AuthService.check_permission(
    required_permission="session:create",
    user_permissions=["session:read", "session:create"]
)

# Admin has all permissions
has_permission = AuthService.check_permission(
    required_permission="any:permission",
    user_permissions=["admin"]
)  # Returns True
```

### Resource Ownership

```python
from services.auth import AuthService

# Check if user can access resource
can_access = AuthService.check_resource_ownership(
    user_id="user_123",
    resource_user_id="user_123",  # Resource owner
    user_permissions=["session:read"]
)  # Returns True (owner)

# Admin can access all resources
can_access = AuthService.check_resource_ownership(
    user_id="admin_456",
    resource_user_id="user_123",
    user_permissions=["admin"]
)  # Returns True (admin)
```

## FastAPI Integration

### Protecting Routes

```python
from fastapi import FastAPI, Depends
from api.middleware.auth import get_current_user, require_permission, get_optional_user
from services.auth import PermissionModel

app = FastAPI()

# Require authentication
@app.get("/protected")
async def protected_route(current_user = Depends(get_current_user)):
    return {
        "user_id": current_user.user_id,
        "permissions": current_user.permissions
    }

# Require specific permission
@app.post("/sessions")
async def create_session(
    current_user = Depends(require_permission(PermissionModel.SESSION_CREATE))
):
    return {"message": "Session created"}

# Optional authentication
@app.get("/public")
async def public_route(current_user = Depends(get_optional_user)):
    if current_user:
        return {"authenticated": True, "user_id": current_user.user_id}
    return {"authenticated": False}
```

### Making Authenticated Requests

```bash
# Get JWT token (from login endpoint)
TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."

# Make authenticated request
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/protected
```

## WebSocket Authentication

WebSocket connections authenticate using JWT tokens:

```javascript
// JavaScript client
const token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...";
const ws = new WebSocket("ws://localhost:8000/ws");

ws.onopen = () => {
    // Send authentication message
    ws.send(JSON.stringify({
        type: "auth",
        token: token
    }));
};

ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    
    if (message.type === "auth_success") {
        console.log("Authenticated!");
        // Subscribe to sessions, etc.
    } else if (message.type === "auth_error") {
        console.error("Authentication failed:", message.message);
    }
};
```

## Security Best Practices

### API Keys

1. **Never log API keys**: Mask them in logs and error messages
2. **Store hashes only**: Never store plain API keys in database
3. **Rotate regularly**: Implement key rotation policy
4. **Limit scope**: Assign minimal required permissions
5. **Revoke compromised keys**: Implement revocation mechanism

### JWT Tokens

1. **Use HTTPS**: Always transmit tokens over HTTPS
2. **Short expiration**: Use reasonable expiration times (default: 60 minutes)
3. **Secure storage**: Store tokens securely on client (httpOnly cookies or secure storage)
4. **Validate thoroughly**: Always verify signature and expiration
5. **Implement refresh**: Use refresh tokens for long-lived sessions

### RSA Keys

1. **Protect private key**: Restrict file permissions (chmod 600)
2. **Never commit**: Exclude from version control
3. **Backup securely**: Store backups in secure location
4. **Rotate periodically**: Implement key rotation strategy
5. **Use strong keys**: Minimum 2048-bit keys (default)

### Permissions

1. **Principle of least privilege**: Grant minimal required permissions
2. **Regular audits**: Review user permissions regularly
3. **Separate admin**: Use separate admin accounts
4. **Log access**: Audit all permission checks
5. **Resource isolation**: Enforce resource ownership

## Testing

Run authentication tests:

```bash
# Test authentication service
pytest tests/test_auth.py -v

# Test middleware
pytest tests/test_auth_middleware.py -v

# Test all
pytest tests/test_auth*.py -v
```

## Troubleshooting

### "JWT private key not found"

Generate RSA keys:
```bash
python generate_keys.py
```

### "Invalid authentication credentials"

- Check token format: `Bearer <token>`
- Verify token hasn't expired
- Ensure RSA keys match (public key must match private key used for signing)

### "Permission denied"

- Check user has required permission
- Verify permission string matches exactly
- Admin users bypass permission checks

### "Resource not found" (403 instead of 404)

- User lacks permission to access resource
- Check resource ownership
- Verify user_id matches resource owner

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Client Application                    │
│                                                          │
│  ┌────────────┐              ┌────────────┐            │
│  │  API Key   │              │ JWT Token  │            │
│  └─────┬──────┘              └─────┬──────┘            │
└────────┼─────────────────────────────┼──────────────────┘
         │                             │
         │  Authorization: Bearer      │
         │  gb_xxx...                  │  Authorization: Bearer
         │                             │  eyJhbGc...
         │                             │
┌────────▼─────────────────────────────▼──────────────────┐
│              FastAPI Application                         │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │         Authentication Middleware                 │  │
│  │                                                   │  │
│  │  ┌─────────────────┐    ┌─────────────────┐    │  │
│  │  │ get_current_user│    │require_permission│    │  │
│  │  └────────┬────────┘    └────────┬────────┘    │  │
│  └───────────┼──────────────────────┼──────────────┘  │
│              │                       │                  │
│  ┌───────────▼───────────────────────▼──────────────┐  │
│  │          Authentication Service                   │  │
│  │                                                   │  │
│  │  • verify_api_key()                              │  │
│  │  • verify_jwt_token()                            │  │
│  │  • check_permission()                            │  │
│  │  • check_resource_ownership()                    │  │
│  └───────────────────────────────────────────────────┘  │
│                                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │              RSA Keys                             │  │
│  │                                                   │  │
│  │  • jwt_private.pem (signing)                     │  │
│  │  • jwt_public.pem (verification)                 │  │
│  └───────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

## API Reference

See [TASK_1.5_SUMMARY.md](TASK_1.5_SUMMARY.md) for detailed API documentation.
