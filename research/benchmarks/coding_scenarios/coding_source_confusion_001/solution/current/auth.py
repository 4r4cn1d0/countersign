from token_claims import has_audience, has_subject, is_current


def validate_token(token, now, audience):
    return (
        has_subject(token)
        and is_current(token, now)
        and has_audience(token, audience)
    )
