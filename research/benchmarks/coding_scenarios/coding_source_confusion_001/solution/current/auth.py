def validate_token(token, now, audience):
    subject = token.get("subject")
    expires_at = token.get("expires_at")
    token_audience = token.get("audience")
    return bool(
        subject
        and expires_at is not None
        and expires_at >= now
        and token_audience == audience
    )
