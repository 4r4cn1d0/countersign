import unittest

from errors import PermanentError, TransientError
from policy import should_retry
from scheduler import next_delay


class TestPolicy(unittest.TestCase):
    def test_only_transient_errors_retry_before_limit(self):
        self.assertTrue(should_retry(TransientError("temporary"), 1, 3))
        self.assertFalse(should_retry(TransientError("temporary"), 3, 3))
        self.assertFalse(should_retry(PermanentError("invalid"), 1, 3))
        self.assertFalse(should_retry(ValueError("unknown"), 1, 3))

    def test_scheduler_uses_capped_exponential_delay(self):
        self.assertEqual(next_delay(4, base=2, cap=10), 10)


if __name__ == "__main__":
    unittest.main()
