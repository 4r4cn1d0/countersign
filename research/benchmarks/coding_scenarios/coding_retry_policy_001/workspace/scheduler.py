from backoff import retry_delay


def next_delay(attempt):
    return retry_delay(attempt)
