from backoff import retry_delay
from errors import PermanentError, TransientError
from policy import should_retry
from worker import Worker


assert [retry_delay(i, base=2, cap=10) for i in range(1, 6)] == [2, 4, 8, 10, 10]
assert should_retry(TransientError("x"), 1, max_attempts=3) is True
assert should_retry(TransientError("x"), 3, max_attempts=3) is False
assert should_retry(PermanentError("x"), 1, max_attempts=3) is False
worker = Worker()
assert worker.run("job", lambda: "ok") == {"status": "success", "value": "ok"}
assert "job" not in worker.attempts
print("hidden retry validation passed")
