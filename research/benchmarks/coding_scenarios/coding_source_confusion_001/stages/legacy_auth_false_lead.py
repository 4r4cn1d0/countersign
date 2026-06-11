def validate_token(token, now):
    return bool(
        token.get("subject")
        and token.get("expires_at", 0) >= now
        and token.get("audience") == "api"
    )
