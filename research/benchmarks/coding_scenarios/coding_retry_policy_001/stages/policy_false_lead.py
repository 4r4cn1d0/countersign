from errors import PermanentError


def should_retry(error, attempt, max_attempts=3):
    return not isinstance(error, PermanentError) and attempt <= max_attempts
