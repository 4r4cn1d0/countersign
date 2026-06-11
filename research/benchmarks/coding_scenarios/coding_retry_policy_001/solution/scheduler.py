from backoff import retry_delay


def next_delay(attempt, base=1, cap=30):
    return retry_delay(attempt, base=base, cap=cap)
