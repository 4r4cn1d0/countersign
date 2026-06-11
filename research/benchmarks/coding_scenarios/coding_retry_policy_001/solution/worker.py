from backoff import retry_delay
from policy import should_retry


class Worker:
    def __init__(self):
        self.attempts = {}

    def run(self, job_id, operation):
        attempt = self.attempts.get(job_id, 0) + 1
        self.attempts[job_id] = attempt
        try:
            value = operation()
        except Exception as error:
            if should_retry(error, attempt):
                return {
                    "status": "retry",
                    "delay": retry_delay(attempt),
                }
            self.attempts.pop(job_id, None)
            return {"status": "failed", "error": str(error)}
        self.attempts.pop(job_id, None)
        return {"status": "success", "value": value}
