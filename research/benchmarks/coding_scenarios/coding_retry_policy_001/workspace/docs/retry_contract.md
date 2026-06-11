# Retry contract

- Retry only `TransientError`.
- Stop when the current attempt reaches `max_attempts`.
- Use capped exponential backoff.
- Clear per-job attempt state after success or terminal failure.
- A scheduler may expose the next delay without mutating worker state.
