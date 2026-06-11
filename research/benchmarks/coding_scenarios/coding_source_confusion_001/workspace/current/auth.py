def validate_token(token, now, audience):
    return bool(token.get("subject"))
