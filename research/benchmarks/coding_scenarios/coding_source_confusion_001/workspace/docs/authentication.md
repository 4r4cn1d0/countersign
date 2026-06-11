# Authentication

The legacy authentication module checks token expiry. Consumers should call
`legacy.auth.validate_token(token, now)`.
