import unittest

from backoff import retry_delay
from errors import PermanentError, TransientError
from worker import Worker


class TestWorker(unittest.TestCase):
    def test_exponential_delay_is_capped(self):
        self.assertEqual(retry_delay(1, base=2, cap=10), 2)
        self.assertEqual(retry_delay(3, base=2, cap=10), 8)
        self.assertEqual(retry_delay(5, base=2, cap=10), 10)

    def test_permanent_failure_does_not_retry(self):
        worker = Worker()

        def fail():
            raise PermanentError("invalid")

        self.assertEqual(worker.run("job", fail)["status"], "failed")

    def test_success_resets_attempt_counter(self):
        worker = Worker()

        def temporary():
            raise TransientError("temporary")

        self.assertEqual(worker.run("job", temporary)["status"], "retry")
        self.assertEqual(worker.run("job", lambda: 42)["status"], "success")
        self.assertNotIn("job", worker.attempts)


if __name__ == "__main__":
    unittest.main()
