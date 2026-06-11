import unittest

from errors import TransientError
from worker import Worker


class TestWorker(unittest.TestCase):
    def test_transient_failure_retries(self):
        worker = Worker()

        def fail():
            raise TransientError("temporary")

        self.assertEqual(worker.run("job", fail)["status"], "retry")


if __name__ == "__main__":
    unittest.main()
