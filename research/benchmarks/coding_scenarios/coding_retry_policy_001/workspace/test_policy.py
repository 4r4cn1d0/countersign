import unittest

from errors import TransientError
from policy import should_retry


class TestPolicy(unittest.TestCase):
    def test_transient_error_retries_before_limit(self):
        self.assertTrue(should_retry(TransientError("temporary"), 1))


if __name__ == "__main__":
    unittest.main()
