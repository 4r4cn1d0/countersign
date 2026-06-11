from current.auth import validate_token


def authorize(token, now, audience):
    return validate_token(token, now=now, audience=audience)
