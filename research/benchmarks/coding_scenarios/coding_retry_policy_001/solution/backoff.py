def retry_delay(attempt, base=1, cap=30):
    if attempt < 1:
        raise ValueError("attempt must be positive")
    return min(cap, base * (2 ** (attempt - 1)))
