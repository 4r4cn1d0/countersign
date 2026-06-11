def has_subject(token):
    return bool(token.get("subject"))


def is_current(token, now):
    expires_at = token.get("expires_at")
    return expires_at is not None and expires_at >= now


def has_audience(token, audience):
    return token.get("audience") == audience
