def should_retry(error, attempt, max_attempts=3):
    return attempt < max_attempts
