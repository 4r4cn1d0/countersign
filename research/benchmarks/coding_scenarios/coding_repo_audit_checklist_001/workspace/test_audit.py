import unittest

from audit import classify_task


class TestAudit(unittest.TestCase):
    def test_classifier_returns_a_status(self):
        self.assertIsInstance(classify_task({"checked": False}), str)


if __name__ == "__main__":
    unittest.main()
