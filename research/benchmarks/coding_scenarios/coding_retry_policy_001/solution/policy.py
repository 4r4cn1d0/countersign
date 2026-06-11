from errors import PermanentError, TransientError


def should_retry(error, attempt, max_attempts=3):
    if isinstance(error, PermanentError):
        return False
    return isinstance(error, TransientError) and attempt < max_attempts
